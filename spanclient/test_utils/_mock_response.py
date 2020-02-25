from dataclasses import dataclass, field
from typing import Optional, Union, Any, List, Mapping, Type
from types import TracebackType

from spantools import MimeType, MimeTypeTolerant, Error, encode_content


_DataType = Union[Mapping[str, Any], List[Mapping[str, Any]]]


@dataclass
class MockResponse:
    """
    Mock response object returned by aiohttp session methods when using
    :func:`testing_utils.mock_aio_response`
    """

    status: int = 200
    """Status code."""
    headers: dict = field(default_factory=dict)
    """Response Headers."""
    _text: Optional[str] = None
    _json: Optional[_DataType] = None
    _yaml: Optional[_DataType] = None
    _bson: Optional[_DataType] = None
    _content: Optional[bytes] = None
    _exception: Optional[BaseException] = None
    _content_type: MimeTypeTolerant = None
    content_type: Optional[str] = field(init=False)
    """Content Type"""

    def __post_init__(self) -> None:
        self.content_type = None
        mock_text = self._text

        if self._json is not None:
            self.mock_json(self._json)
        elif self._yaml is not None:
            self.mock_yaml(self._yaml)
        elif self._bson is not None:
            self.mock_bson(self._bson)
        elif mock_text is not None:
            self.mock_text(mock_text)

        if self._content_type is not None:
            self.content_type = MimeType.to_string(self._content_type)  # type: ignore

        if self.content_type is not None:
            MimeType.add_to_headers(self.headers, self.content_type)

        if self._exception is not None:
            self.mock_exception(self._exception)

    async def json(self) -> Optional[_DataType]:
        """Loaded json data."""
        return self._json

    async def read(self) -> Optional[bytes]:
        """Raw bytes."""
        if self._content is None:
            return b""
        return self._content

    async def text(self) -> Optional[str]:
        """Decoded bytes."""
        return self._text

    async def __aenter__(self) -> "MockResponse":
        return self

    def mock_status(self, code: int) -> None:
        """Set status of mock."""
        self.status = code

    def _text_from_content(self) -> None:
        self._text = self._content.decode()  # type: ignore

    def mock_text(self, text: str) -> None:
        """Set mock content to text."""
        if self.content_type is None:
            self.content_type = MimeType.TEXT.value
        self._content = encode_content(text, MimeType.TEXT)
        self._text_from_content()

    def mock_json(self, data: _DataType) -> None:
        """Set mock content to json-encoded data."""
        if self.content_type is None:
            self.content_type = MimeType.JSON.value
        self._json = data
        self._content = encode_content(data, MimeType.JSON)
        self._text_from_content()

    def mock_yaml(self, data: _DataType) -> None:
        """Set mock content to yaml-encoded data."""
        if self.content_type is None:
            self.content_type = MimeType.YAML.value
        self._yaml = data
        self._content = encode_content(data, MimeType.YAML)
        self._text_from_content()

    def mock_bson(self, data: _DataType) -> None:
        """Set mock content to bson-encoded data."""
        if self.content_type is None:
            self.content_type = MimeType.BSON.value
        self._bson = data
        self._content = encode_content(data, MimeType.BSON)

    def mock_exception(self, exc_base: BaseException) -> None:
        """Mock spanserver-style exception headers."""
        self._exception = exc_base
        error_data, exc = Error.from_exception(exc_base)
        error_data.to_headers(self.headers)
        self.status = exc.http_code

    def mock_content(self, content: bytes) -> None:
        """Mock content bytes."""
        self._content = content

    async def __aexit__(
        self,
        exc_type: Type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        pass
