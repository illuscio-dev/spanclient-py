import gemma
from marshmallow import Schema
from aiohttp import ClientResponse
from typing import Union, Tuple, Optional, Dict, Callable, Any, AsyncGenerator, Type

from spantools import (
    MimeType,
    decode_content,
    NoErrorReturnedError,
    Error,
    ContentDecodeError as ContentDecodeBase,
    ContentTypeUnknownError as ContentTypeUnknownBase,
    DecoderIndexType,
    DEFAULT_DECODERS,
)
from spantools.errors_api import APIError, NothingToReturnError

from ._typing import ModelType
from ._response_data import ResponseData
from ._client import ClientSession
from .test_utils import StatusMismatchError, ContentDecodeError, ContentTypeUnknownError


# GEMMA CACHED OBJECTS
DEFAULT_SURVEYOR = gemma.Surveyor()
DEFAULT_CARTOGRAPHER = gemma.Cartographer()


def _check_status_code(
    received_code: int,
    valid_status_codes: Union[int, Tuple[int, ...]],
    response: ClientResponse,
) -> None:
    """Checks that the incoming code matches the expected codes."""
    if isinstance(valid_status_codes, int):
        valid_status_codes = (valid_status_codes,)

    if received_code not in valid_status_codes:
        raise StatusMismatchError(
            f"Expected code(s) {valid_status_codes} but got {received_code}",
            response=response,
        )


def _default_updater(current: Any, new: Any) -> None:
    DEFAULT_CARTOGRAPHER.map(new, current, surveyor=DEFAULT_SURVEYOR)


def _update_data(
    current_data_object: ModelType,
    new_data_object: Any,
    object_updater: Optional[Callable[[ModelType, Any], None]] = None,
) -> None:
    """Updates current object in place with data from new object."""

    if object_updater is None:
        object_updater = _default_updater

    object_updater(current_data_object, new_data_object)


async def handle_response_aio(
    response: ClientResponse,
    valid_status_codes: Union[int, Tuple[int, ...]] = 200,
    data_schema: Optional[Union[Schema, MimeType]] = None,
    api_errors_additional: Optional[Dict[int, Type[APIError]]] = None,
    current_data_object: Optional[ModelType] = None,
    data_object_updater: Optional[Callable[[ModelType, Any], None]] = None,
    decoders: DecoderIndexType = DEFAULT_DECODERS,
) -> ResponseData:
    """
    Examines response from SpanReed service and raises reported errors.

    :param response: from aiohttp
    :param valid_status_codes: Valid return http code(s).
    :param data_schema: Schema object for loading responses.
    :param api_errors_additional: Code, Error Class Mapping of Additional APIError types
        the response may return.
    :param current_data_object: Current object which represents response payload. Will
        be updated in-place with response data.
    :param data_object_updater: Callable which takes args:
        (current_data_object, new_data_object). Used to update current_data_object
        in place of the default updater.

    :return: Loaded data, raw data mapping (dict or bson record).

    :raises ResponseStatusError: If status code does match.
    :raises ContentTypeUnknownError: If content-type is not a type that is known.
    :raises marshmallow.ValidationError: If data not consistent with schema.
    """

    # Try to raise error, catch if it does not exist.
    try:
        raise Error.from_headers(response.headers).to_exception(api_errors_additional)
    except NoErrorReturnedError:
        pass

    _check_status_code(
        received_code=response.status,
        valid_status_codes=valid_status_codes,
        response=response,
    )

    content = await response.read()

    if content or data_schema is not None:
        try:
            loaded_data, decoded_data = decode_content(
                content=content,
                mimetype=MimeType.from_headers(response.headers),
                data_schema=data_schema,
                allow_sniff=True,
                decoders=decoders,
            )
        except ContentDecodeBase as error:
            raise ContentDecodeError(str(error), response=response)
        except ContentTypeUnknownBase as error:
            raise ContentTypeUnknownError(str(error), response=response)
    else:
        loaded_data, decoded_data = None, None

    if current_data_object is not None:
        _update_data(
            current_data_object=current_data_object,
            new_data_object=loaded_data,
            object_updater=data_object_updater,
        )
        loaded_data = current_data_object

    return ResponseData(resp=response, loaded=loaded_data, decoded=decoded_data)


async def iter_paged_aio(
    session: ClientSession,
    url_base: str,
    method: str = "get",
    offset_start: int = 0,
    limit: int = 200,
    params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
    json: Optional[dict] = None,
    data: Optional[Union[str, bytes]] = None,
    valid_status_codes: Union[int, Tuple[int, ...]] = 200,
    data_schema: Optional[Union[Schema, MimeType]] = None,
) -> AsyncGenerator[ResponseData, None]:
    """
    Handle paged responses. Automatically fetches paged until no more items returned.

    :param session: session to use
    :param url_base: url without paging params (other params should be included).
    :param offset_start: Beginning offset.
    :param limit: Number of objects to be fetched per request.
    :param headers: Request headers to send.
    :param params: URL parameters.
    :param method: request method to use ('get', 'post', etc.).
    :param json: json data to send with each request.
    :param data: text or binary data to send with each request.
    :param valid_status_codes: Valid status codes for checking response.
    :param data_schema: Schema for loading returned data.

    :return: loaded_obj, raw data mapping (dict or bson record).
    """
    if headers is None:
        headers = dict()

    if params is None:
        params = dict()

    # Set up paging params and update with passed params.
    params_start = {"paging-offset": str(offset_start), "paging-limit": str(limit)}
    params_start.update(params)

    method_func = getattr(session, method)
    response_future = method_func(
        url_base, params=params_start, headers=headers, data=data, json=json
    )

    next_future = response_future

    # next_future will be the request for the next page so long as a next page url is
    # supplied in the response headers.
    while next_future is not None:

        response: ClientResponse
        async with next_future as response:

            next_page_url = response.headers.get("paging-next")
            if next_page_url is not None:
                method_func = getattr(session, method)
                next_future = method_func(
                    next_page_url, headers=headers, data=data, json=json
                )
            else:
                next_future = None

            try:
                this_page = await handle_response_aio(
                    response,
                    valid_status_codes=valid_status_codes,
                    data_schema=data_schema,
                )
            except NothingToReturnError:
                # It may be the case that resources were deleted or the total number
                # / next page was not reported correctly. We break if a NothingToReturn
                # error is sent back.
                break

            for loaded_obj, decoded_obj in zip(this_page.loaded, this_page.decoded):
                response_info = ResponseData(
                    resp=response, loaded=loaded_obj, decoded=decoded_obj
                )
                yield response_info
