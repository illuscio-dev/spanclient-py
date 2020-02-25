from typing import Union, List, TypeVar
from bson.raw_bson import RawBSONDocument


# TYPING
ContentType = Union[dict, List[dict], RawBSONDocument, List[RawBSONDocument]]
ModelType = TypeVar("ModelType")
