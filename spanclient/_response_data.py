from aiohttp import ClientResponse
from dataclasses import dataclass
from typing import Any


@dataclass
class ResponseData:
    """Holds information about handled response."""

    resp: ClientResponse
    """aiohttp response object."""
    loaded: Any
    """loaded body data from schema."""
    decoded: Any
    """raw unloaded mapping of body values (result of json/bson/yaml decode)"""
