import copy
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, Union

from spantools import (
    encode_content,
    MimeType,
    convert_params_headers,
    PagingReq,
    ContentTypeUnknownError as ContentTypeUnknownBase,
)

from ._handle_responses import handle_response_aio
from ._response_data import ResponseData
from .test_utils import ContentTypeUnknownError


@dataclass
class PagingReqClient(PagingReq):
    """Paging info for requests."""

    max_pages: int
    """Maximum number of pages to return before halting."""
    page_to_fetch: int
    """
    The page that will be fetched by this request. This is supplied as information for
    the user.
    """
    offset_start: int = 0
    """Where to start the offset from if not defined in the decorator."""


@dataclass
class ClientRequest:
    client: "SpanClient"
    """The aiohttp.ClientSession to execute the request with"""
    endpoint_settings: "_EndpointSettings"
    """Endpoint params for the endpoint of the request."""
    path_params: Dict[str, Any] = field(default_factory=dict)
    """Keyword values for endpoint pattern."""
    query_params: Dict[str, Any] = field(default_factory=dict)
    """Additional params to add to this request url."""
    projection: Dict[str, int] = field(default_factory=dict)
    """
    Projection settings for response body trimming. Added to query params with
    ``'project.{value}'`` prefix.
    """
    headers: Dict[str, Any] = field(default_factory=dict)
    """Additional HTTP headers to send with this request."""
    media: Optional[Dict[str, Any]] = None
    """Media data to be serialized for send."""
    mimetype_send: Optional[Union[MimeType, str]] = None
    """Mimetype value to use on request."""
    mimetype_accept: Optional[Union[MimeType, str]] = None
    """Mimetype value to use on request."""
    update_obj: Optional[Any] = None
    """
    Current object which represents response payload. Will be updated in-place with
    response data.
    """
    executed: bool = False
    """Whether this request has been executed."""
    return_info: Optional[bool] = None
    """
    Whether to return full info instead of loaded / decoded body.
    """
    _paging: Optional[PagingReqClient] = None

    @property
    def paging(self) -> PagingReqClient:
        if self._paging is None:
            raise TypeError("Handler is not paged")
        else:
            return self._paging

    async def execute(self) -> ResponseData:
        """
        Executes request and handles response from spanreed endpoint.
        """
        params = copy.copy(self.endpoint_settings.query_params)
        params.update(self.query_params)
        for key, value in self.projection.items():
            params["project." + key] = str(value)
        convert_params_headers(params)

        if self._paging is not None:
            self._paging.offset += self._paging.offset_start
            params["paging-offset"] = str(self._paging.offset)
            params["paging-limit"] = str(self._paging.limit)

        headers = copy.copy(self.endpoint_settings.headers)
        headers.update(self.headers)
        convert_params_headers(self.headers)

        if self.mimetype_accept is not None:
            headers["Accept"] = MimeType.to_string(self.mimetype_accept)

        base_url = (
            f"{self.client.protocol}://{self.client.host_name}"
            f"{self.endpoint_settings.endpoint}"
        )
        url = base_url.format(**self.path_params)

        req_schema = self.endpoint_settings.req_schema

        try:
            data = encode_content(
                content=self.media,
                mimetype=self.mimetype_send,
                headers=headers,
                data_schema=req_schema,
                encoders=self.client._ENCODERS,
            )
        except ContentTypeUnknownBase as error:
            raise ContentTypeUnknownError(str(error), response=None)

        # allow for method to be passed in caps.
        method = self.endpoint_settings.method.lower()
        method_func = getattr(self.client.session, method)

        response = await method_func(url=url, params=params, headers=headers, data=data)

        self.executed = True

        return await handle_response_aio(
            response=response,
            valid_status_codes=self.endpoint_settings.resp_codes,
            data_schema=self.endpoint_settings.resp_schema,
            api_errors_additional=self.client.api_error_index,
            current_data_object=self.update_obj,
            data_object_updater=self.endpoint_settings.data_updater,
            decoders=self.client._DECODERS,
        )


typing_help = False
if typing_help:
    from ._endpoint_wrapper import _EndpointSettings
    from ._client import SpanClient
