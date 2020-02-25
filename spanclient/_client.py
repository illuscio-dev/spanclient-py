import copy
from typing import Optional, List, Dict, Type
from types import TracebackType
from aiohttp import ClientSession

from spantools import (
    EncoderType,
    DecoderType,
    EncoderIndexType,
    DecoderIndexType,
    DEFAULT_ENCODERS,
    DEFAULT_DECODERS,
    MimeTypeTolerant,
    MimeType,
)
from spantools.errors_api import APIError, ERRORS_INDEXED

from ._endpoint_wrapper import EndpointWrapper
from ._request_obj import ClientRequest

handles = EndpointWrapper()


def register_mimetype(
    mimetype: MimeTypeTolerant, encoder: EncoderType, decoder: DecoderType
) -> None:
    try:
        mimetype = MimeType.from_name(mimetype)
    except ValueError:
        pass

    SpanClient._ENCODERS[mimetype] = encoder
    SpanClient._DECODERS[mimetype] = decoder


class SpanClient:
    """
    Base class for building async http clients for specific API's. Should be used in a
    context block.
    """

    REQ = ClientRequest(client=None, endpoint_settings=None)  # type: ignore
    DEFAULT_HOST_NAME: Optional[str] = None
    """Override to default API hostname when subclassing."""
    DEFAULT_PORT: Optional[int] = None
    """Override to default API port when subclassing."""
    DEFAULT_PROTOCOL: str = "http"
    """Can be overridden if default protocol should be https"""

    API_ERRORS_ADDITIONAL: Optional[List[Type[APIError]]] = None
    """List of additional :class:`errors_api.APIError` exceptions for error-catching."""

    _ENCODERS: EncoderIndexType = copy.copy(DEFAULT_ENCODERS)
    _DECODERS: DecoderIndexType = copy.copy(DEFAULT_DECODERS)

    def __init__(
        self,
        host_name: Optional[str] = None,
        port: Optional[int] = None,
        protocol: Optional[str] = None,
        session: Optional[ClientSession] = None,
    ):
        """
        :param host_name: Hostname of API to use if not default.
        :param protocol: Protocol to use if not default.
        :param session: Existing aio_http session to us. New session created if none
            passed.
        """
        if host_name is None:
            if self.DEFAULT_HOST_NAME is None:
                raise ValueError(
                    f"{self.__class__.__name__} does not have a default hostname."
                    f" Please supply one."
                )
            else:
                host_name = self.DEFAULT_HOST_NAME

        if port is None:
            port = self.DEFAULT_PORT

        if port is not None:
            host_name += f":{port}"

        if protocol is None:
            protocol = self.DEFAULT_PROTOCOL

        api_errors_additional = self.API_ERRORS_ADDITIONAL
        if api_errors_additional is None:
            api_errors_additional = list()

        api_error_index = copy.copy(ERRORS_INDEXED)
        api_errors_additional_indexed = {e.api_code: e for e in api_errors_additional}
        api_error_index.update(api_errors_additional_indexed)

        self.protocol: str = protocol
        self.host_name: str = host_name
        self._session: Optional[ClientSession] = session
        self.api_error_index: Dict[int, Type[APIError]] = api_error_index

    async def __aenter__(self) -> "SpanClient":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        await self.close()

    async def start(self) -> None:
        """
        Starts the session. Invoked by async with on context open. Broken out to be
        overridable.
        """
        _ = self.session

    async def close(self) -> None:
        """
        Closes the session. Invoked by async with on context close. Broken out to be
        overridable.
        """
        await self.session.close()

    @property
    def session(self) -> ClientSession:
        """Session object."""
        if self._session is None:
            self._session = ClientSession()
        return self._session
