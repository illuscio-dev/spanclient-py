from dataclasses import dataclass, field
from typing import Optional, Union, Callable, Any, MutableMapping, cast
from bson.raw_bson import RawBSONDocument

from spantools import (
    MimeType,
    MimeTypeTolerant,
    decode_content,
    convert_params_headers,
    ContentTypeUnknownError,
    NoContentError,
)

from ._errors import (
    HeadersMismatchError,
    URLMismatchError,
    DataValidationError,
    DataTypeValidationError,
    ParamsMismatchError,
)
from ._mock_response import MockResponse


ReqMappingType = Optional[MutableMapping[str, Any]]


@dataclass
class RequestValidator:
    """Used to validate aiohttp method params."""

    url: Optional[str] = None
    """
    Expected URL value, does not include any query params, but should include path
    params.
    """
    headers: ReqMappingType = None
    """
    Expected request header keys and values. Error is only thrown if a header is missing
    or incorrect, NOT if there are other headers present. These are the minimum
    required headers.
    """
    params: ReqMappingType = None
    """
    Expected URL query param keys and values. Error is only thrown if a param is
    missing or incorrect, NOT if there are other params present. These are the minimum
    required headers.
    """
    content_type: MimeTypeTolerant = None
    """Expected value of ``'Content-Type'`` header."""
    media: Optional[Union[list, dict, str, bytes]] = None
    """Expected media."""

    custom_hook: Optional[Callable[["RequestValidator", MockResponse], None]] = None
    """Custom validation callable."""

    req_url: Optional[str] = field(init=False)
    req_params: MutableMapping[str, str] = field(init=False)
    req_headers: MutableMapping[str, str] = field(init=False)
    req_data: Optional[bytes] = field(init=False)

    req_data_decoded: Optional[Any] = field(init=False)

    def __post_init__(self) -> None:
        convert_params_headers(self.headers)
        convert_params_headers(self.params)

        if self.content_type is not None:
            if self.headers is None:
                self.headers = dict()
            MimeType.add_to_headers(self.headers, self.content_type)

    def validate_request(
        self,
        req_url: str,
        req_headers: MutableMapping[str, str],
        req_params: MutableMapping[str, str],
        req_data: Optional[bytes],
        mock_response: MockResponse,
    ) -> None:
        self.req_url = req_url
        self.req_params = req_params
        self.req_headers = req_headers
        self.req_data = req_data
        self.req_data_decoded = None

        self.validate_url()
        self.validate_headers()
        self.validate_params()

        mimetype = MimeType.from_headers(req_headers)
        self.validate_media(mimetype=mimetype)
        self.validate_media_type(mimetype)

        if self.custom_hook is not None:
            self.custom_hook(self, mock_response)

    def validate_url(self) -> None:
        if self.url is None:
            return

        try:
            assert self.req_url == self.url
        except AssertionError:
            raise URLMismatchError(
                f"Expected: {self.url}, got {self.req_url}", response=None
            )

    def validate_headers(self) -> None:
        if self.headers is None:
            return

        self.headers = cast(MutableMapping[str, str], self.headers)

        for key, value in self.headers.items():
            try:
                check_value = self.req_headers[key]
            except KeyError:
                raise HeadersMismatchError(
                    f"'{key}' not found in request headers", response=None
                )

            try:
                assert check_value == value
            except AssertionError:
                raise HeadersMismatchError(
                    f"Header '{key}' has value of '{check_value}', expected '{value}'",
                    response=None,
                )

    def validate_params(self) -> None:
        if self.params is None:
            return

        self.params = cast(MutableMapping[str, str], self.params)

        for key, value in self.params.items():
            try:
                check_value = self.req_params[key]
            except KeyError:
                raise ParamsMismatchError(
                    f"'{key}' not found in request params", response=None
                )

            try:
                assert check_value == value
            except AssertionError:
                raise ParamsMismatchError(
                    f"Param '{key}' has value of '{check_value}', expected '{value}'",
                    response=None,
                )

    def validate_media_type(self, mimetype: MimeTypeTolerant) -> None:
        if self.req_data is None:
            return

        try:
            decoded, _ = decode_content(self.req_data, mimetype=mimetype)
        except ContentTypeUnknownError:
            return
        except NoContentError:
            # This used to return None, now we need to catch the error.
            decoded = None
        except BaseException:
            raise DataTypeValidationError(
                f"Request content was not expected type {mimetype}", response=None
            )

        if self.req_data_decoded is None:
            self.req_data_decoded = decoded

    @staticmethod
    def _cast_bson_to_dict(check_media: Any) -> Any:
        if isinstance(check_media, RawBSONDocument):
            check_media = dict(check_media)
        elif isinstance(check_media, list):
            first = check_media[0]
            if isinstance(first, RawBSONDocument):
                check_media = [dict(doc) for doc in check_media]

        return check_media

    def validate_media(self, mimetype: MimeTypeTolerant) -> None:

        if self.media is None:
            return

        if self.req_data is None:
            raise DataValidationError(
                f"Expected: {repr(self.media)}, got {None}", response=None
            )

        try:
            self.req_data_decoded, _ = decode_content(
                content=self.req_data, mimetype=mimetype, allow_sniff=True
            )
        except ContentTypeUnknownError:
            pass

        # This handles casting bson docs (which are not comparable) to dicts / lists
        self.req_data_decoded = self._cast_bson_to_dict(self.req_data_decoded)

        if isinstance(self.media, type(self.req_data)):
            check_data = self.req_data
        else:
            check_data = self.req_data_decoded

        # Check the media
        try:
            assert check_data == self.media
        except AssertionError:
            raise DataValidationError(
                f"Expected: {repr(self.media)}, got {repr(check_data)}", response=None
            )
