import functools
import copy
from dataclasses import dataclass
from marshmallow import Schema
from typing import (
    Optional,
    MutableMapping,
    Any,
    Union,
    Callable,
    Tuple,
    Dict,
    AsyncGenerator,
    Generator,
    Sequence,
)

from spantools import MimeType, convert_params_headers, MimeTypeTolerant
from spantools.errors_api import NothingToReturnError

from ._typing import ModelType
from ._request_obj import ClientRequest, PagingReqClient
from ._response_data import ResponseData


class _PagedHalt(BaseException):
    """Raised to halt further paging."""


@dataclass
class _EndpointSettings:
    endpoint: str
    """URL endpoint."""
    method: str
    """HTTP method to use for request."""
    query_params: MutableMapping[str, str]
    """URL params to use on EVERY endpoint request."""
    headers: MutableMapping[str, str]
    """HTTP header values to send on EVERY endpoint request."""
    req_schema: Optional[Schema]
    """Req body schema to use for decoding request body."""
    resp_codes: Tuple[int, ...]
    """Single or tuple of valid HTTP response codes."""
    resp_schema: Optional[Schema]
    """Marshmallow schema for decoding response object."""
    data_updater: Optional[Callable[[ModelType, Any], None]]
    """
    Custom updater for mapping new data to existing data object. Takes arguments
    ``(current_object, new_object)`` amd returns ``None``
    """


class EndpointWrapper:
    """
    Wraps endpoints for client. When an attribute is fetched from this class, a partial
    version of :func:`EndpointWrapper.generic` is returned with the attribute name
    pre-placed in the ``method`` parameter.

    This class is not accessed directly, but invoked through an instance:
    ``spanclient.handles``.
    """

    def __getattribute__(self, item: str) -> Any:
        if not item.startswith("_") and item != "paged":
            return functools.partial(super().__getattribute__("generic"), item)
        else:
            return super().__getattribute__(item)

    @staticmethod
    async def _endpoint_wrapper(
        client: "SpanClient",
        endpoint_settings: _EndpointSettings,
        mimetype_send: MimeTypeTolerant,
        mimetype_accept: MimeTypeTolerant,
        return_info: bool,
        handler: Callable,
        args: Sequence[Any],
        kwargs: MutableMapping[str, Any],
    ) -> Any:
        endpoint_settings = copy.copy(endpoint_settings)

        try:
            req: ClientRequest = kwargs["req"]
        except KeyError:
            req = ClientRequest(client, endpoint_settings=endpoint_settings)
        else:
            req.endpoint_settings = endpoint_settings

        req.mimetype_send = mimetype_send
        req.mimetype_accept = mimetype_accept
        kwargs["req"] = req
        if req.return_info is None:
            req.return_info = return_info

        result = await handler(client, *args, **kwargs)

        if not req.executed:
            result_data = await req.execute()
            if return_info or req.return_info:
                result = result_data
            elif result_data.loaded is not None:
                result = result_data.loaded
            else:
                result = result_data.resp

        return result

    @staticmethod
    def generic(
        method: str,
        endpoint: str,
        query_params: Optional[MutableMapping[str, Any]] = None,
        headers: Optional[MutableMapping[str, Any]] = None,
        mimetype_send: Optional[Union[str, MimeType]] = None,
        mimetype_accept: Optional[Union[str, MimeType]] = None,
        req_schema: Optional[Schema] = None,
        resp_codes: Union[int, Tuple[int, ...]] = 200,
        resp_schema: Optional[Schema] = None,
        data_updater: Optional[Callable[[ModelType, Any], None]] = None,
        return_info: bool = False,
    ) -> Callable:
        """
        Decorator that is ACTUALLY called decorating an endpoint method.

        :param method: HTTP method -- GET, POST, PUT, etc. Filled in automatically
            by the decorator invoked, ie: ``@handles.get``
        :param endpoint: Endpoint path. Can use f-string syntax for path params.
            ex: /wizards/{wizard_id}
        :param query_params: URL query params to apply to all requests from this method.
        :param headers: HTTP headers to apply to all requests made from this method.
        :param mimetype_send: Mimetype to use when encoding content. Added to the
            ``'Content-Type'`` header.
        :param mimetype_accept: Mimetype to request from server. Added to the
            ``'Accept'`` header.
        :param req_schema: Schema for dumping request body media.
        :param resp_codes: Valid response codes.
        :param resp_schema: Schema for loading response body content.
        :param data_updater: To use when updating existing data objects in-place.
        :param return_info: Whether to return a :class:`ReturnData` instance in place of
            the decoded / loaded response body.
        :return: Method decorator.

        :raises StatusMismatchError: When response status does not match ``resp_codes``.
        :raises ContentTypeUnknownError: When ``ClientRequest.media`` is not bytes
            but an unregistered mimetype is given to ``mimetype_send`` or
            ``ClientRequest.mimetype_send``.
        :raises ContentEncodeError: When error occurs encoding request body.
        :raises ContentDecodeError: When error occurs decoding response body.
        """
        if query_params is None:
            query_params = dict()
        if headers is None:
            headers = dict()

        convert_params_headers(query_params)
        convert_params_headers(headers)

        if isinstance(resp_codes, int):
            resp_codes = (resp_codes,)

        endpoint_settings = _EndpointSettings(
            method=method,
            endpoint=endpoint,
            query_params=query_params,
            headers=headers,
            req_schema=req_schema,
            resp_codes=resp_codes,
            resp_schema=resp_schema,
            data_updater=data_updater,
        )

        def decorator(handler: Callable) -> Callable:
            @functools.wraps(handler)
            async def wrapper(client: "SpanClient", *args: Any, **kwargs: Any) -> Any:
                result = await EndpointWrapper._endpoint_wrapper(
                    client=client,
                    endpoint_settings=endpoint_settings,
                    mimetype_send=mimetype_send,
                    mimetype_accept=mimetype_accept,
                    return_info=return_info,
                    handler=handler,
                    args=args,
                    kwargs=kwargs,
                )

                return result

            return wrapper

        return decorator

    @staticmethod
    def get(
        endpoint: str,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        mimetype_send: Optional[Union[str, MimeType]] = None,
        mimetype_accept: Optional[Union[str, MimeType]] = None,
        req_schema: Optional[Schema] = None,
        resp_codes: Union[int, Tuple[int, ...]] = 200,
        resp_schema: Optional[Schema] = None,
        data_updater: Optional[Callable[[Any, Any], None]] = None,
        return_info: bool = False,
    ) -> Callable:
        """For IDE code-completion. Alias of :func:`EndpointWrapper.generic`"""

    @staticmethod
    def post(
        endpoint: str,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        mimetype_send: Optional[Union[str, MimeType]] = None,
        mimetype_accept: Optional[Union[str, MimeType]] = None,
        req_schema: Optional[Schema] = None,
        resp_codes: Union[int, Tuple[int, ...]] = 200,
        resp_schema: Optional[Schema] = None,
        data_updater: Optional[Callable[[Any, Any], None]] = None,
        return_info: bool = False,
    ) -> Callable:
        """For IDE code-completion. Alias of :func:`EndpointWrapper.generic`"""

    @staticmethod
    def put(
        endpoint: str,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        mimetype_send: Optional[Union[str, MimeType]] = None,
        mimetype_accept: Optional[Union[str, MimeType]] = None,
        req_schema: Optional[Schema] = None,
        resp_codes: Union[int, Tuple[int, ...]] = 200,
        resp_schema: Optional[Schema] = None,
        data_updater: Optional[Callable[[Any, Any], None]] = None,
        return_info: bool = False,
    ) -> Callable:
        """For IDE code-completion. Alias of :func:`EndpointWrapper.generic`"""

    @staticmethod
    def patch(
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        mimetype_send: Optional[Union[str, MimeType]] = None,
        mimetype_accept: Optional[Union[str, MimeType]] = None,
        req_schema: Optional[Schema] = None,
        resp_codes: Union[int, Tuple[int, ...]] = 200,
        resp_schema: Optional[Schema] = None,
        data_updater: Optional[Callable[[Any, Any], None]] = None,
        return_info: bool = False,
    ) -> Callable:
        """For IDE code-completion. Alias of :func:`EndpointWrapper.generic`"""

    @staticmethod
    def delete(
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        mimetype_send: Optional[Union[str, MimeType]] = None,
        mimetype_accept: Optional[Union[str, MimeType]] = None,
        req_schema: Optional[Schema] = None,
        resp_codes: Union[int, Tuple[int, ...]] = 200,
        resp_schema: Optional[Schema] = None,
        data_updater: Optional[Callable[[Any, Any], None]] = None,
        return_info: bool = False,
    ) -> Callable:
        pass

    @staticmethod
    def copy(
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        mimetype_send: Optional[Union[str, MimeType]] = None,
        mimetype_accept: Optional[Union[str, MimeType]] = None,
        req_schema: Optional[Schema] = None,
        resp_codes: Union[int, Tuple[int, ...]] = 200,
        resp_schema: Optional[Schema] = None,
        data_updater: Optional[Callable[[Any, Any], None]] = None,
        return_info: bool = False,
    ) -> Callable:
        """For IDE code-completion. Alias of :func:`EndpointWrapper.generic`"""

    @staticmethod
    def _paged_init_req(
        client: "SpanClient",
        offset_params: int,
        limit: int,
        max_pages: int,
        page_to_fetch: int,
    ) -> ClientRequest:
        paging = PagingReqClient(  # type: ignore
            offset=offset_params,
            limit=limit,
            max_pages=max_pages,
            page_to_fetch=page_to_fetch,
        )
        req = ClientRequest(client, None)  # type: ignore
        req._paging = paging
        req.return_info = True

        return req

    @staticmethod
    def _paged_yield_result_items(result: Any) -> Generator[Any, None, None]:
        if isinstance(result, ResponseData):
            page_next: Union[str, bool] = result.resp.headers.get("paging-next", False)
            if result.loaded is not None:
                items = result.loaded
            else:
                items = [result.resp]
        else:
            page_next = True
            items = result

        for item in items:
            yield item

        if page_next is False:
            raise _PagedHalt("Stop")

    @staticmethod
    def paged(offset: int = 0, limit: int = 50, max_pages: int = -1) -> Callable:
        """
        Turns method into an async generator to seamlessly handle paged responses.

        :param offset: Beginning offset to use.
        :param limit: Default limit to use.
        :param max_pages: Maximum number of pages to return when called.
        :return: Wrapped function.

        THIS METHOD MUST BE USED ON TOP OF A GENERIC ``handles`` decorator.
        """

        def decorator(handler: Callable) -> Callable:
            @functools.wraps(handler)
            async def wrapper(
                client: "SpanClient", *args: Any, **kwargs: Any
            ) -> AsyncGenerator:

                offset_param = offset
                pages_fetched = 0

                while True:
                    req = EndpointWrapper._paged_init_req(
                        client,
                        offset_param,
                        limit,
                        max_pages,
                        page_to_fetch=pages_fetched + 1,
                    )
                    kwargs["req"] = req

                    try:
                        result = await handler(client, *args, **kwargs)
                    except NothingToReturnError:
                        break

                    try:
                        for item in EndpointWrapper._paged_yield_result_items(result):
                            yield item
                    except _PagedHalt:
                        break

                    pages_fetched += 1
                    if pages_fetched == req.paging.max_pages:
                        break

                    offset_param += req.paging.limit

            return wrapper

        return decorator


typing_help = False
if typing_help:
    from ._client import SpanClient
