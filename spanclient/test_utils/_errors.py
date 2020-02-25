from typing import Optional
from spantools import (
    ContentDecodeError as ContentDecodeBase,
    ContentEncodeError,
    SpanError,
    ContentTypeUnknownError as ContentTypeUnknownBase,
)
from aiohttp import ClientResponse


(ContentEncodeError)


class ResponseValidationError(SpanError):
    """Base Error for Exceptions Thrown by mismatched Responses."""

    def __init__(self, msg: str, response: Optional[ClientResponse]) -> None:
        self.response: Optional[ClientResponse] = response
        super().__init__(msg)


class ContentDecodeError(ResponseValidationError, ContentDecodeBase):
    """Error decoding response body."""


class ContentTypeUnknownError(ResponseValidationError, ContentTypeUnknownBase):
    """Could not handle unknown content type."""


class StatusMismatchError(ResponseValidationError):
    """Status code does not match expected."""


class WrongExceptionError(ResponseValidationError):
    """Error in headers does not match expected exception."""


class DataValidationError(ResponseValidationError):
    """Response data does not match schema."""


class DataTypeValidationError(ResponseValidationError):
    """Response data does not match schema."""


class TextValidationError(DataValidationError):
    """Response text does not match supplied value."""


class HeadersMismatchError(ResponseValidationError):
    """Headers do not match expected values."""


class ParamsMismatchError(ResponseValidationError):
    """Headers do not match expected values."""


class PagingMismatchError(ResponseValidationError):
    """Paging does not match expected values."""


class URLMismatchError(ResponseValidationError):
    """Request URL does not match expected url."""
