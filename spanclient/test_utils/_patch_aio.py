import aiohttp
import functools
from dataclasses import dataclass
from asynctest import patch
from typing import (
    Generator,
    Optional,
    MutableMapping,
    Sequence,
    Union,
    Callable,
    TypeVar,
    List,
    Any,
    Tuple,
)

from ._mock_response import MockResponse
from ._req_validator import RequestValidator

_ResponseListType = List[Optional[MockResponse]]
_ValidatorListType = List[Optional[RequestValidator]]

_ResponseType = Optional[Union[MockResponse, _ResponseListType]]
_ValidatorType = Optional[Union[RequestValidator, _ValidatorListType]]
_MockConfigIterType = Generator[
    Tuple[Optional[MockResponse], Optional[RequestValidator]], None, None
]


@dataclass
class MockConfig:
    """
    Configuration of aiohttp mocks for single http method during a test. Passed into
    test through ``{method}_config = None`` keyword-only parameter.
    """

    resp: Optional[_ResponseListType]
    """List of response objects to return."""
    req_validator: Optional[_ValidatorListType]
    """List of validators to cycle through to validate aiohttp method parameters."""

    def __iter__(self) -> _MockConfigIterType:
        mock_resp_gen = _endless_generator(self.resp)
        req_validator_gen = _endless_generator(self.req_validator)  # type: ignore

        for req_mock in zip(mock_resp_gen, req_validator_gen):
            yield req_mock


async def _mock_aiohttp_method(
    self: aiohttp.ClientSession,
    mock_config: MockConfig,
    url: str,
    params: MutableMapping[str, str],
    headers: MutableMapping[str, str],
    data: Optional[bytes] = None,
) -> MockResponse:
    # NOTE ON ARGS: params and headers would normally have a default of None, but our
    # client framework ALWAYS passes a dict, even if it is emtpy
    mock_resp, req_validator = next(mock_config)  # type: ignore

    if req_validator is not None:
        req_validator.validate_request(
            req_url=url,
            req_params=params,
            req_headers=headers,
            req_data=data,
            mock_response=mock_resp,
        )

    return mock_resp


GenType = TypeVar("GenType")


def _endless_generator(
    seq: Optional[Sequence[Optional[GenType]]],
) -> Generator[Optional[GenType], None, None]:
    while True:
        if not seq:
            yield None
        else:
            for item in seq:
                yield item


def mock_aiohttp(
    method: str, resp: _ResponseType = None, req_validator: _ValidatorType = None
) -> Callable:
    """
    Decorator for patching aio_http method with request validator that returns a
    MockResponse.

    :param method: HTTP method to replace: GET, POST, etc.
    :param resp: Mock response object(s) to return. Objects are returned
        endlessly, so if one mock response is passed, it will be returned every time
        the aiohttp method is invoked, but if three are passed, they will be rotated
        through like so: 1, 2, 3, 1, 2, 3, 1, ...
    :param req_validator: Validator(s) to check passed aiohttp params. Like mock
        responses, validators are cycled through endlessly to check each response.
    :return: Pytest decorator.
    """
    method = method.lower()

    if isinstance(resp, MockResponse):
        resp = [resp]

    if isinstance(req_validator, RequestValidator):
        req_validator = [req_validator]

    mock_config = MockConfig(resp, req_validator)

    mock_func = functools.partialmethod(_mock_aiohttp_method, (m for m in mock_config))

    def decorator(test_method: Callable) -> Callable:
        @functools.wraps(test_method)
        async def wrapped_method(*args: Any, **kwargs: Any) -> Any:
            config_key = method + "_config"
            kwargs[config_key] = mock_config

            try:
                return await test_method(*args, **kwargs)
            except TypeError as error:
                kwargs.pop(config_key)

                check_message = f"got an unexpected keyword argument '{config_key}'"
                if check_message in str(error):
                    return await test_method(*args, **kwargs)
                else:
                    raise error

        return patch.object(aiohttp.ClientSession, method, mock_func)(wrapped_method)

    return decorator
