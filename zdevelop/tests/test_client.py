import pytest
import rapidjson as json
import uuid
import aiohttp
import yaml
import io
import csv
import copy
from aiostream.stream import enumerate as aio_enumeerate
from dataclasses import dataclass
from grahamcracker import DataSchema, schema_for
from bson import BSON
from bson.raw_bson import RawBSONDocument
from typing import AsyncGenerator, List, Optional, Callable, Dict, Any

from spantools import errors_api

from spanclient import (
    handle_response_aio,
    iter_paged_aio,
    StatusMismatchError,
    SpanClient,
    ContentDecodeError,
    handles,
    ClientRequest,
    ContentTypeUnknownError,
    test_utils,
    MimeType,
    register_mimetype,
)
from spanclient.test_utils import MockResponse, MockConfig, RequestValidator


class MockSession:
    def __init__(
        self,
        method_list: List[str],
        response_list: List[MockResponse],
        call_checks: Optional[List[Callable]] = None,
    ):
        if call_checks is None:
            call_checks = list()

        self._response_list: List[MockResponse] = response_list
        self._call_checks: List[Callable] = call_checks
        self._method_list: List[str] = method_list

    def __getattr__(self, item: str):
        if not item.startswith("_"):
            assert item == self._method_list.pop()
            return self._route
        else:
            return super().__getattribute__(item)

    def _route(
        self,
        url: str,
        *,
        headers: Optional[dict] = None,
        json: Optional[dict] = None,
        data: Optional[bytes] = None,
        params: Optional[dict] = None,
    ):
        return self._response_list.pop(0)


@dataclass
class Name:
    first: str
    last: str


@schema_for(Name)
class NameSchema(DataSchema[Name]):
    pass


@dataclass
class NameID:
    id: uuid.UUID
    first: str
    last: str


@schema_for(NameID)
class NameIDSchema(DataSchema[NameID]):
    pass


class TestMockResponse:
    def test_default_status(self):
        r = MockResponse()
        assert r.status == 200

    def test_content_type_mimetyp(self):
        r = MockResponse(status=200, _content_type=MimeType.JSON)
        assert r.content_type == "application/json"

    @pytest.mark.parametrize("arg", ["_text", "_json", "_yaml", "_bson"])
    def test_mimetype_override(self, arg):
        if arg == "_text":
            data = "some data"
        else:
            data = {"key": "value"}

        kwargs = {arg: data, "_content_type": "application/custom"}
        r = MockResponse(**kwargs)

        assert r.content_type == "application/custom"
        assert getattr(r, arg) is not None

    @pytest.mark.asyncio
    async def test_json(self):
        r = MockResponse(status=200, _json={"key": "value"})

        assert await r.json() == {"key": "value"}
        assert await r.text() == json.dumps({"key": "value"})
        assert await r.read() == json.dumps({"key": "value"}).encode()

        assert r.content_type == "application/json"

    @pytest.mark.asyncio
    async def test_text(self):
        r = MockResponse(status=200, _text="test")

        assert await r.text() == "test"
        assert await r.read() == "test".encode()

        assert r.content_type == "text/plain"


class TestStatusCodes:
    @pytest.mark.asyncio
    async def test_status_code_pass(self):
        r = MockResponse(status=200)
        await handle_response_aio(r)

    @pytest.mark.asyncio
    async def test_status_code_pass_non_default(self):
        r = MockResponse(status=201)
        await handle_response_aio(r, valid_status_codes=201)

    @pytest.mark.asyncio
    async def test_status_code_pass_tuple(self):
        r = MockResponse(status=201)
        await handle_response_aio(r, valid_status_codes=(200, 201))

    @pytest.mark.asyncio
    async def test_status_code_fail(self):
        r = MockResponse(status=400)
        with pytest.raises(StatusMismatchError):
            try:
                await handle_response_aio(r)
            except StatusMismatchError as error:
                assert error.response is r
                raise error

    @pytest.mark.asyncio
    async def test_status_code_fail_non_default(self):
        r = MockResponse(status=400)
        with pytest.raises(StatusMismatchError):
            try:
                await handle_response_aio(r, valid_status_codes=201)
            except StatusMismatchError as error:
                assert error.response is r
                raise error

    @pytest.mark.asyncio
    async def test_status_code_fail_tuple(self):
        r = MockResponse(status=400)
        with pytest.raises(StatusMismatchError):
            try:
                await handle_response_aio(r, valid_status_codes=(200, 201))
            except StatusMismatchError as error:
                assert error.response is r
                raise error


class TestDataLoad:
    @pytest.mark.asyncio
    async def test_no_data_returned(self):
        r = MockResponse(status=200)

        r_info = await handle_response_aio(r)

        assert r_info.loaded is None
        assert r_info.decoded is None

    @pytest.mark.asyncio
    async def test_text(self):
        r = MockResponse(status=200, _text="test text")

        r_info = await handle_response_aio(r)

        assert r_info.loaded == "test text"
        assert r_info.decoded == "test text"

    @pytest.mark.asyncio
    async def test_json(self):
        r = MockResponse(status=200, _json={"first": "Harry", "last": "Potter"})
        r.headers["Content-Type"] = "application/json"

        r_info = await handle_response_aio(r, data_schema=NameSchema())

        assert r_info.loaded == Name("Harry", "Potter")
        assert r_info.decoded == {"first": "Harry", "last": "Potter"}

    @pytest.mark.asyncio
    async def test_json_no_schema(self):
        r = MockResponse(status=200, _json={"first": "Harry", "last": "Potter"})
        r.headers["Content-Type"] = "application/json"

        r_info = await handle_response_aio(r)

        assert r_info.loaded == {"first": "Harry", "last": "Potter"}
        assert r_info.decoded == {"first": "Harry", "last": "Potter"}

    @pytest.mark.asyncio
    async def test_bson(self):
        r = MockResponse(
            status=200, _content=BSON.encode({"first": "Harry", "last": "Potter"})
        )
        r.headers["Content-Type"] = "application/bson"

        r_info = await handle_response_aio(r, data_schema=NameSchema())

        assert r_info.loaded == Name("Harry", "Potter")
        assert isinstance(r_info.decoded, RawBSONDocument)
        assert dict(r_info.decoded) == {"first": "Harry", "last": "Potter"}

    @pytest.mark.asyncio
    async def test_bson_no_schema(self):
        r = MockResponse(
            status=200, _content=BSON.encode({"first": "Harry", "last": "Potter"})
        )
        r.headers["Content-Type"] = "application/bson"

        r_info = await handle_response_aio(r)

        assert dict(r_info.loaded) == {"first": "Harry", "last": "Potter"}
        assert isinstance(r_info.decoded, RawBSONDocument)
        assert dict(r_info.decoded) == {"first": "Harry", "last": "Potter"}

    @pytest.mark.asyncio
    async def test_unknown_no_content_type_header(self):
        r = MockResponse(status=200)

        with pytest.raises(ContentDecodeError):
            try:
                await handle_response_aio(r, data_schema=NameSchema())
            except ContentDecodeError as error:
                assert error.response is r
                raise error

    @pytest.mark.asyncio
    async def test_unknown_content(self):
        r = MockResponse(status=200, _content=b"some content")
        r.headers["Content-Type"] = "application/unknown"

        with pytest.raises(ContentTypeUnknownError):
            try:
                await handle_response_aio(r, data_schema=NameSchema())
            except ContentTypeUnknownError as error:
                assert error.response is r
                raise error


class TestErrorHandling:
    @pytest.mark.parametrize(
        "error_type",
        [
            errors_api.APIError,
            errors_api.InvalidMethodError,
            errors_api.RequestValidationError,
            errors_api.ResponseValidationError,
            errors_api.NothingToReturnError,
        ],
    )
    @pytest.mark.asyncio
    async def test_api_error(self, error_type: errors_api.APIError):
        error_id = uuid.uuid4()

        r = MockResponse(status=200)
        r.headers["error-name"] = error_type.__name__
        r.headers["error-code"] = str(error_type.api_code)
        r.headers["error-data"] = json.dumps({"key": "value"})
        r.headers["error-message"] = "some message"
        r.headers["error-id"] = str(error_id)

        try:
            await handle_response_aio(r)
        except BaseException as error:
            assert isinstance(error, error_type)
            assert error.id == error_id
            assert error.error_data == {"key": "value"}
            assert str(error) == "some message"
        else:
            raise AssertionError("error not raised")


class TestPaging:
    @pytest.mark.asyncio
    async def test_handle_normal(self):
        methods = ["get", "get", "get"]
        harry_json = {"first": "Harry", "last": "Potter"}
        headers = {"paging-next": "/some/url", "Content-Type": "application/json"}

        mock_response_1 = MockResponse(status=200, _json=[harry_json, harry_json])
        mock_response_1.headers = headers

        mock_response_2 = MockResponse(status=200, _json=[harry_json, harry_json])
        mock_response_2.headers = headers

        mock_response_3 = MockResponse(status=200, _json=[harry_json, harry_json])
        mock_response_3.headers = {
            "paging-next": None,
            "Content-Type": "application/json",
        }

        responses = [mock_response_1, mock_response_2, mock_response_3]

        mock_session = MockSession(method_list=methods, response_list=responses)

        item_iter = aio_enumeerate(
            iter_paged_aio(
                session=mock_session,
                url_base="/test/base",
                limit=2,
                data_schema=NameSchema(many=True),
            ),
            start=1,
        )

        i = 0
        async for i, r_info in item_iter:
            print(r_info)
            assert r_info.loaded == Name("Harry", "Potter")
            assert r_info.decoded == {"first": "Harry", "last": "Potter"}

        assert i == 6

    @pytest.mark.asyncio
    async def test_handle_nothing_to_return(self):
        methods = ["get", "get", "get", "get", "get"]
        harry_json = {"first": "Harry", "last": "Potter"}
        headers = {"paging-next": "/some/url", "Content-Type": "application/json"}

        mock_response_1 = MockResponse(status=200, _json=[harry_json, harry_json])
        mock_response_1.headers = headers

        mock_response_2 = MockResponse(status=200, _json=[harry_json, harry_json])
        mock_response_2.headers = headers

        mock_response_3 = MockResponse(status=200, _json=[harry_json, harry_json])
        mock_response_3.headers = headers

        mock_response_4 = MockResponse(status=400)

        mock_response_4.headers = {
            "paging-next": "/some/url",
            "Content-Type": "application/json",
            "error-code": errors_api.NothingToReturnError.api_code,
            "error-name": errors_api.NothingToReturnError.__name__,
            "error-message": "Some Message",
            "error-id": str(uuid.uuid4()),
        }

        responses = [
            mock_response_1,
            mock_response_2,
            mock_response_3,
            mock_response_4,
            None,
        ]

        mock_session = MockSession(method_list=methods, response_list=responses)

        item_iter = aio_enumeerate(
            iter_paged_aio(
                session=mock_session,
                url_base="/test/base",
                limit=2,
                data_schema=NameSchema(many=True),
            ),
            start=1,
        )

        i = 0
        async for i, r_info in item_iter:
            print(r_info)
            assert r_info.loaded == Name("Harry", "Potter")
            assert r_info.decoded == {"first": "Harry", "last": "Potter"}

        assert i == 6


def validate_name_post(validator: RequestValidator, response: MockResponse):
    TestSpanClient.VALIDATOR_TRIGGERED = True
    assert validator.req_data_decoded == NameSchema().dump(
        {"first": "Harry", "last": "Potter"}
    )


class TestClientInit:
    def test_default_host(self):
        class APIClient(SpanClient):
            DEFAULT_HOST_NAME = "SomeHost"

        client = APIClient()
        assert client.host_name == "SomeHost"

    def test_no_host_raises(self):
        class APIClient(SpanClient):
            pass

        with pytest.raises(ValueError):
            _ = APIClient()

    def test_default_port(self):
        class APIClient(SpanClient):
            DEFAULT_PORT = 8080

        client = APIClient(host_name="SomeHost")
        assert client.host_name == "SomeHost:8080"


class TestSpanClient:
    UUID1 = uuid.uuid4()

    @pytest.mark.asyncio
    async def test_context_spawn_session(self):
        class APIClient(SpanClient):
            pass

        client = APIClient(host_name="api-host")
        assert client._session is None

        async with client:
            assert client._session is not None

    @pytest.mark.asyncio
    async def test_prop_spawn_session(self):
        class APIClient(SpanClient):
            pass

        client = APIClient(host_name="api-host")
        assert client._session is None
        assert client.session is not None
        assert client._session is not None

        session = client.session

        async with client:
            assert client._session is session
            assert client.session is session

    @test_utils.mock_aiohttp(
        method="GET",
        resp=test_utils.MockResponse(
            status=201, _json={"id": str(UUID1), "first": "Harry", "last": "Potter"}
        ),
        req_validator=test_utils.RequestValidator(url=f"http://api-host/names/{UUID1}"),
    )
    @pytest.mark.asyncio
    async def test_basic_client(self):
        class APIClient(SpanClient):
            @handles.get("/names/{name_id}", resp_codes=201, resp_schema=NameIDSchema())
            async def name_fetch(
                self, name_id: uuid.UUID, *, req: ClientRequest
            ) -> NameID:

                req.path_params["name_id"] = name_id

        client = APIClient(host_name="api-host")

        name = await client.name_fetch(TestSpanClient.UUID1)
        assert name.id == TestSpanClient.UUID1
        assert name.first == "Harry"
        assert name.last == "Potter"

    @test_utils.mock_aiohttp(
        method="GET",
        resp=test_utils.MockResponse(),
        req_validator=test_utils.RequestValidator(url=f"http://api-host/changed"),
    )
    @pytest.mark.asyncio
    async def test_basic_client_endpoint_setting_alter(self):
        class APIClient(SpanClient):
            @handles.get("/original")
            async def name_fetch(self, *, req: ClientRequest):
                print("test")
                assert req.endpoint_settings.endpoint == "/original"
                req.endpoint_settings.endpoint = "/changed"

        client = APIClient(host_name="api-host")

        await client.name_fetch()
        await client.name_fetch()

    @test_utils.mock_aiohttp(
        method="GET",
        resp=(
            test_utils.MockResponse(status=200, _text="response 1"),
            test_utils.MockResponse(status=201, _text="response 2"),
        ),
    )
    @pytest.mark.asyncio
    async def test_basic_client_double_response(self):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=(200, 201))
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                info = await req.execute()
                return info.resp

        client = APIClient(host_name="api-host")

        resp1 = await client.name_fetch()
        assert resp1.status == 200
        assert await resp1.text() == "response 1"

        resp2 = await client.name_fetch()
        assert resp2.status == 201
        assert await resp2.text() == "response 2"

    @test_utils.mock_aiohttp(
        method="GET",
        resp=(
            test_utils.MockResponse(status=200, _text="response 1"),
            test_utils.MockResponse(status=201, _text="response 2"),
        ),
        req_validator=(
            test_utils.RequestValidator(url=f"http://api-host/names/1"),
            test_utils.RequestValidator(url=f"http://api-host/names/2"),
        ),
    )
    @pytest.mark.asyncio
    async def test_basic_client_double_validate(self):
        class APIClient(SpanClient):
            @handles.get("/names/{num}", resp_codes=(200, 201))
            async def name_fetch(
                self, num: int, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                req.path_params["num"] = num
                info = await req.execute()
                return info.resp

        client = APIClient(host_name="api-host")

        resp1 = await client.name_fetch(1)
        assert resp1.status == 200
        assert await resp1.text() == "response 1"

        resp2 = await client.name_fetch(2)
        assert resp2.status == 201
        assert await resp2.text() == "response 2"

    @test_utils.mock_aiohttp(
        method="GET",
        resp=(
            test_utils.MockResponse(status=200, _text="response 1"),
            test_utils.MockResponse(status=400, _text="response 2"),
        ),
    )
    @pytest.mark.asyncio
    async def test_basic_client_double_response_bad_status(self):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=(200, 201))
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                info = await req.execute()
                return info.resp

        client = APIClient(host_name="api-host")

        resp1 = await client.name_fetch()
        assert resp1.status == 200
        assert await resp1.text() == "response 1"

        with pytest.raises(test_utils.StatusMismatchError):
            await client.name_fetch()

    @test_utils.mock_aiohttp(
        method="GET",
        resp=(
            test_utils.MockResponse(status=200, _text="response 1"),
            test_utils.MockResponse(status=201, _text="response 2"),
        ),
        req_validator=(
            test_utils.RequestValidator(url=f"http://api-host/names/1"),
            test_utils.RequestValidator(url=f"http://api-host/names/2"),
        ),
    )
    @pytest.mark.asyncio
    async def test_basic_client_double_validate_fail_second(self):
        class APIClient(SpanClient):
            @handles.get("/names/{num}", resp_codes=(200, 201))
            async def name_fetch(
                self, num: int, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                req.path_params["num"] = num
                info = await req.execute()
                return info.resp

        client = APIClient(host_name="api-host")

        resp1 = await client.name_fetch(1)
        assert resp1.status == 200
        assert await resp1.text() == "response 1"

        with pytest.raises(test_utils.URLMismatchError):
            await client.name_fetch(3)

    VALIDATOR_TRIGGERED = False

    @test_utils.mock_aiohttp(
        method="POST",
        resp=test_utils.MockResponse(
            status=201, _json={"id": str(UUID1), "first": "Harry", "last": "Potter"}
        ),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names/{UUID1}",
            params={"limit": 10, "offset": 0},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            media={"first": "Harry", "last": "Potter"},
            custom_hook=validate_name_post,
        ),
    )
    @pytest.mark.asyncio
    async def test_req_validation_client(self):
        class APIClient(SpanClient):
            @handles.post(
                "/names/{name_id}",
                req_schema=NameIDSchema(exclude=("id",)),
                query_params={"limit": 10, "offset": 0},
                headers={"Accept": "application/json"},
                resp_codes=201,
                resp_schema=NameIDSchema(),
            )
            async def name_fetch(
                self, name_id: uuid.UUID, *, req: ClientRequest
            ) -> NameID:
                req.media = Name("Harry", "Potter")
                req.path_params["name_id"] = name_id

        client = APIClient(host_name="api-host")

        assert TestSpanClient.VALIDATOR_TRIGGERED is False

        name = await client.name_fetch(TestSpanClient.UUID1)
        assert name.id == TestSpanClient.UUID1
        assert name.first == "Harry"
        assert name.last == "Potter"

        assert TestSpanClient.VALIDATOR_TRIGGERED is True

    @test_utils.mock_aiohttp(
        method="POST",
        resp=test_utils.MockResponse(status=201),
        req_validator=test_utils.RequestValidator(url=f"http://api-host/names/{UUID1}"),
    )
    @pytest.mark.asyncio
    async def test_result_no_data(self):
        class APIClient(SpanClient):
            @handles.post("/names/{name_id}", resp_codes=201)
            async def name_fetch(
                self, name_id: uuid.UUID, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                req.path_params["name_id"] = name_id

        client = APIClient(host_name="api-host")

        resp = await client.name_fetch(TestSpanClient.UUID1)
        assert resp.status == 201

    @test_utils.mock_aiohttp(
        method="POST",
        resp=test_utils.MockResponse(status=201),
        req_validator=test_utils.RequestValidator(url=f"http://api-host/names"),
    )
    @pytest.mark.asyncio
    async def test_result_returned(self):
        class APIClient(SpanClient):
            @handles.post("/names", resp_codes=201)
            async def name_fetch(
                self, name_id: uuid.UUID, *, req: ClientRequest
            ) -> str:
                await req.execute()
                return "custom"

        client = APIClient(host_name="api-host")

        resp = await client.name_fetch(TestSpanClient.UUID1)
        assert resp == "custom"

    @test_utils.mock_aiohttp(
        method="GET",
        resp=test_utils.MockResponse(
            status=200, _json={"id": str(UUID1), "first": "Hermione", "last": "Granger"}
        ),
        req_validator=test_utils.RequestValidator(url=f"http://api-host/names/{UUID1}"),
    )
    @pytest.mark.asyncio
    async def test_update_object(self):
        class APIClient(SpanClient):
            @handles.get(
                "/names/{name_id}",
                resp_codes=200,
                resp_schema=NameIDSchema(load_dataclass=False),
            )
            async def name_fetch(self, name: NameID, *, req: ClientRequest) -> NameID:

                req.path_params["name_id"] = name.id
                req.update_obj = name

        client = APIClient(host_name="api-host")
        name = NameID(TestSpanClient.UUID1, "Harry", "Potter")

        name_returned = await client.name_fetch(name)

        assert name is name_returned

        assert name.id == TestSpanClient.UUID1
        assert name.first == "Hermione"
        assert name.last == "Granger"

    @test_utils.mock_aiohttp(
        method="GET",
        resp=test_utils.MockResponse(
            status=200, _json={"id": str(UUID1), "first": "Hermione", "last": "Granger"}
        ),
        req_validator=test_utils.RequestValidator(url=f"http://api-host/names/{UUID1}"),
    )
    @pytest.mark.asyncio
    async def test_update_object_custom(self):
        def custom_updater(current: Name, new: dict):
            current.id = new["id"]
            current.first = new["first"] + "-custom"
            current.last = new["last"] + "-custom"

        class APIClient(SpanClient):
            @handles.get(
                "/names/{name_id}",
                resp_codes=200,
                resp_schema=NameIDSchema(load_dataclass=False),
                data_updater=custom_updater,
            )
            async def name_fetch(self, name: NameID, *, req: ClientRequest) -> NameID:

                req.path_params["name_id"] = name.id
                req.update_obj = name

        client = APIClient(host_name="api-host")
        name = NameID(TestSpanClient.UUID1, "Harry", "Potter")

        name_returned = await client.name_fetch(name)

        assert name is name_returned

        assert name.id == TestSpanClient.UUID1
        assert name.first == "Hermione-custom"
        assert name.last == "Granger-custom"

    @test_utils.mock_aiohttp(
        method="POST",
        resp=test_utils.MockResponse(status=200),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names", media="Harry Potter"
        ),
    )
    @pytest.mark.asyncio
    async def test_send_implicit_text(self):
        class APIClient(SpanClient):
            @handles.post("/names", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                req.media = "Harry Potter"

        client = APIClient(host_name="api-host")

        resp = await client.name_fetch()
        assert resp.status == 200

    @test_utils.mock_aiohttp(
        method="POST",
        resp=test_utils.MockResponse(status=200),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names", media=b"Some Bin Data"
        ),
    )
    @pytest.mark.asyncio
    async def test_send_unknown_mimetype(self):
        class APIClient(SpanClient):
            @handles.post("/names", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                req.media = b"Some Bin Data"
                req.mimetype_send = "application/unknown"

        client = APIClient(host_name="api-host")

        resp = await client.name_fetch()
        assert resp.status == 200

    @test_utils.mock_aiohttp(
        method="POST",
        resp=test_utils.MockResponse(status=200),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names", media=b"Some Bin Data"
        ),
    )
    @pytest.mark.asyncio
    async def test_send_unknown_mimetype_error(self):
        class APIClient(SpanClient):
            @handles.post("/names", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                req.media = {"key": "value"}
                req.mimetype_send = "application/unknown"

        client = APIClient(host_name="api-host")

        with pytest.raises(ContentTypeUnknownError):
            await client.name_fetch()

    @test_utils.mock_aiohttp(
        method="POST",
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names",
            media={"first": "Harry", "last": "Potter"},
            headers={"Content-Type": MimeType.YAML.value},
        ),
        resp=test_utils.MockResponse(
            status=200, _yaml={"first": "Ron", "last": "Weasley"}
        ),
    )
    @pytest.mark.asyncio
    async def test_yaml_round_trip_schema(self):
        class APIClient(SpanClient):
            @handles.post(
                "/names",
                req_schema=NameSchema(),
                resp_codes=200,
                resp_schema=NameSchema(),
            )
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                req.media = Name("Harry", "Potter")
                req.mimetype_send = MimeType.YAML

        client = APIClient(host_name="api-host")

        response = await client.name_fetch()
        assert response == Name("Ron", "Weasley")

    @test_utils.mock_aiohttp(
        method="POST",
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names",
            media={"first": "Harry", "last": "Potter"},
            headers={"Content-Type": MimeType.BSON.value},
        ),
        resp=test_utils.MockResponse(
            status=200, _bson={"first": "Ron", "last": "Weasley"}
        ),
    )
    @pytest.mark.asyncio
    async def test_bson_round_trip_schema(self):
        class APIClient(SpanClient):
            @handles.post(
                "/names",
                req_schema=NameSchema(),
                resp_codes=200,
                resp_schema=NameSchema(),
            )
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                req.media = Name("Harry", "Potter")
                req.mimetype_send = MimeType.BSON

        client = APIClient(host_name="api-host")

        response = await client.name_fetch()
        assert response == Name("Ron", "Weasley")

    @test_utils.mock_aiohttp(
        method="POST",
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names",
            media=[
                {"first": "Harry", "last": "Potter"},
                {"first": "Draco", "last": "Malfoy"},
            ],
            headers={"Content-Type": MimeType.BSON.value},
        ),
        resp=test_utils.MockResponse(
            status=200,
            _bson=[
                {"first": "Ron", "last": "Weasley"},
                {"first": "Hermione", "last": "Granger"},
            ],
        ),
    )
    @pytest.mark.asyncio
    async def test_bson_list_round_trip_schema(self):
        class APIClient(SpanClient):
            @handles.post(
                "/names",
                req_schema=NameSchema(many=True),
                resp_codes=200,
                resp_schema=NameSchema(many=True),
            )
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                req.media = [Name("Harry", "Potter"), Name("Draco", "Malfoy")]
                req.mimetype_send = MimeType.BSON

        client = APIClient(host_name="api-host")

        response = await client.name_fetch()
        assert response == [Name("Ron", "Weasley"), Name("Hermione", "Granger")]

    @test_utils.mock_aiohttp(
        method="POST",
        resp=test_utils.MockResponse(
            status=200,
            _content=yaml.safe_dump({"first": "Ron", "last": "Weasley"}).encode(),
        ),
    )
    @pytest.mark.asyncio
    async def test_sniff_return_content(self):
        class APIClient(SpanClient):
            @handles.post("/names", resp_codes=200, resp_schema=NameSchema())
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                pass

        client = APIClient(host_name="api-host")

        response = await client.name_fetch()
        assert response == Name("Ron", "Weasley")

    @test_utils.mock_aiohttp(
        method="POST",
        resp=test_utils.MockResponse(status=200),
        req_validator=test_utils.RequestValidator(
            headers={"Accept": MimeType.YAML.value}
        ),
    )
    @pytest.mark.asyncio
    async def test_accept_mimetype(self):
        class APIClient(SpanClient):
            @handles.post("/names", mimetype_accept=MimeType.YAML, resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                pass

        client = APIClient(host_name="api-host")

        await client.name_fetch()

    @test_utils.mock_aiohttp(
        method="GET",
        req_validator=[
            # Validator 1
            test_utils.RequestValidator(
                headers={"Accept": MimeType.JSON.value},
                params={"paging-offset": 0, "paging-limit": 2},
            ),
            # Validator 2
            test_utils.RequestValidator(
                headers={"Accept": MimeType.JSON.value},
                params={"paging-offset": 2, "paging-limit": 2},
            ),
        ],
        resp=[
            # Response 1
            test_utils.MockResponse(
                status=200,
                headers={"paging-next": "some_page"},
                _json=[
                    {"first": "Harry", "last": "Potter"},
                    {"first": "Ron", "last": "Weasley"},
                ],
            ),
            # Response 2
            test_utils.MockResponse(
                status=200,
                _json=[
                    {"first": "Hermione", "last": "Granger"},
                    {"first": "Draco", "last": "Malfoy"},
                ],
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_paged(self):
        class APIClient(SpanClient):
            @handles.paged(limit=2)
            @handles.get(
                "/names",
                mimetype_accept=MimeType.JSON,
                resp_codes=200,
                resp_schema=NameSchema(many=True),
            )
            async def name_fetch(
                self, *, req: ClientRequest
            ) -> AsyncGenerator[Name, None]:
                pass

        client = APIClient(host_name="api-host")

        names = list()
        async for name in client.name_fetch():
            print(name)
            names.append(name)

        assert names == [
            Name("Harry", "Potter"),
            Name("Ron", "Weasley"),
            Name("Hermione", "Granger"),
            Name("Draco", "Malfoy"),
        ]

    @test_utils.mock_aiohttp(
        method="GET",
        req_validator=[
            # Validator 1
            test_utils.RequestValidator(
                headers={"Accept": MimeType.BSON.value},
                params={"paging-offset": 0, "paging-limit": 2},
            )
        ],
        resp=[
            # Response 1
            test_utils.MockResponse(
                status=200, _bson=[{"first": "Harry", "last": "Potter"}]
            )
        ],
    )
    @pytest.mark.asyncio
    async def test_paged_single_bson(self):
        class APIClient(SpanClient):
            @handles.paged(limit=2)
            @handles.get(
                "/names",
                mimetype_accept=MimeType.BSON,
                resp_codes=200,
                resp_schema=NameSchema(many=True),
            )
            async def name_fetch(
                self, *, req: ClientRequest
            ) -> AsyncGenerator[Name, None]:
                pass

        client = APIClient(host_name="api-host")

        names = list()
        async for name in client.name_fetch():
            print(name)
            names.append(name)

        assert names == [Name("Harry", "Potter")]

    @test_utils.mock_aiohttp(
        method="GET",
        req_validator=[
            # Validator 1
            test_utils.RequestValidator(
                headers={"Accept": MimeType.JSON.value},
                params={"paging-offset": 0, "paging-limit": 2},
            ),
            # Validator 2
            test_utils.RequestValidator(
                headers={"Accept": MimeType.JSON.value},
                params={"paging-offset": 2, "paging-limit": 2},
            ),
        ],
        resp=[
            # Response 1
            test_utils.MockResponse(
                status=200,
                headers={"paging-next": "some_page"},
                _json=[
                    {"first": "Harry", "last": "Potter"},
                    {"first": "Ron", "last": "Weasley"},
                ],
            ),
            # Response 2
            test_utils.MockResponse(
                status=200,
                _json=[
                    {"first": "Hermione", "last": "Granger"},
                    {"first": "Draco", "last": "Malfoy"},
                ],
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_paged_limit_override(self):
        class APIClient(SpanClient):
            @handles.paged(limit=50)
            @handles.get(
                "/names",
                mimetype_accept=MimeType.JSON,
                resp_codes=200,
                resp_schema=NameSchema(many=True),
            )
            async def name_fetch(
                self, limit: int, *, req: ClientRequest
            ) -> AsyncGenerator[Name, None]:
                req.paging.limit = limit

        client = APIClient(host_name="api-host")

        names = list()
        async for name in client.name_fetch(2):
            print(name)
            names.append(name)

        assert names == [
            Name("Harry", "Potter"),
            Name("Ron", "Weasley"),
            Name("Hermione", "Granger"),
            Name("Draco", "Malfoy"),
        ]

    @test_utils.mock_aiohttp(
        method="GET",
        req_validator=[
            # Validator 1
            test_utils.RequestValidator(
                headers={"Accept": MimeType.JSON.value},
                params={"paging-offset": 2, "paging-limit": 2},
            ),
            # Validator 2
            test_utils.RequestValidator(
                headers={"Accept": MimeType.JSON.value},
                params={"paging-offset": 4, "paging-limit": 2},
            ),
        ],
        resp=[
            # Response 1
            test_utils.MockResponse(
                status=200,
                headers={"paging-next": "some_page"},
                _json=[
                    {"first": "Harry", "last": "Potter"},
                    {"first": "Ron", "last": "Weasley"},
                ],
            ),
            # Response 2
            test_utils.MockResponse(
                status=200,
                _json=[
                    {"first": "Hermione", "last": "Granger"},
                    {"first": "Draco", "last": "Malfoy"},
                ],
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_paged_offset_override(self):
        class APIClient(SpanClient):
            @handles.paged(limit=50)
            @handles.get(
                "/names",
                mimetype_accept=MimeType.JSON,
                resp_codes=200,
                resp_schema=NameSchema(many=True),
            )
            async def name_fetch(
                self, skip: int, *, req: ClientRequest
            ) -> AsyncGenerator[Name, None]:
                req.paging.offset_start = skip
                req.paging.limit = 2

        client = APIClient(host_name="api-host")

        names = list()
        async for name in client.name_fetch(2):
            print(name)
            names.append(name)

        assert names == [
            Name("Harry", "Potter"),
            Name("Ron", "Weasley"),
            Name("Hermione", "Granger"),
            Name("Draco", "Malfoy"),
        ]

    @test_utils.mock_aiohttp(
        method="GET",
        req_validator=[
            # Validator 1
            test_utils.RequestValidator(
                headers={"Accept": MimeType.JSON.value},
                params={"paging-offset": 0, "paging-limit": 2},
            ),
            # Validator 2
            test_utils.RequestValidator(
                headers={"Accept": MimeType.JSON.value},
                params={"paging-offset": 2, "paging-limit": 2},
            ),
            # Validator 3
            test_utils.RequestValidator(
                headers={"Accept": MimeType.JSON.value},
                params={"paging-offset": 4, "paging-limit": 2},
            ),
        ],
        resp=[
            # Response 1
            test_utils.MockResponse(
                status=200,
                headers={"paging-next": "some_page"},
                _json=[
                    {"first": "Harry", "last": "Potter"},
                    {"first": "Ron", "last": "Weasley"},
                ],
            ),
            # Response 2
            test_utils.MockResponse(
                status=200,
                _json=[
                    {"first": "Hermione", "last": "Granger"},
                    {"first": "Draco", "last": "Malfoy"},
                ],
            ),
            # Response 3
            test_utils.MockResponse(
                status=200,
                _exception=errors_api.NothingToReturnError(
                    message="No Items to return", error_id=uuid.uuid4()
                ),
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_paged_manual(self):
        class APIClient(SpanClient):
            @handles.paged(limit=2)
            @handles.get(
                "/names",
                mimetype_accept=MimeType.JSON,
                resp_codes=200,
                resp_schema=NameSchema(many=True),
            )
            async def name_fetch(
                self, *, req: ClientRequest
            ) -> AsyncGenerator[Name, None]:
                result = await req.execute()
                return result.loaded

        client = APIClient(host_name="api-host")

        names = list()
        async for name in client.name_fetch():
            names.append(name)

        assert names == [
            Name("Harry", "Potter"),
            Name("Ron", "Weasley"),
            Name("Hermione", "Granger"),
            Name("Draco", "Malfoy"),
        ]

    @test_utils.mock_aiohttp(
        method="GET",
        req_validator=[
            # Validator 1
            test_utils.RequestValidator(
                headers={"Accept": MimeType.JSON.value},
                params={"paging-offset": 0, "paging-limit": 2},
            ),
            # Validator 2
            test_utils.RequestValidator(
                headers={"Accept": MimeType.JSON.value},
                params={"paging-offset": 2, "paging-limit": 2},
            ),
        ],
        resp=[
            # Response 1
            test_utils.MockResponse(status=200, headers={"paging-next": "some_page"}),
            # Response 2
            test_utils.MockResponse(status=200),
        ],
    )
    @pytest.mark.asyncio
    async def test_paged_empty_body(self):
        class APIClient(SpanClient):
            @handles.paged(limit=2)
            @handles.get("/names", mimetype_accept=MimeType.JSON, resp_codes=200)
            async def name_fetch(
                self, *, req: ClientRequest
            ) -> AsyncGenerator[Name, None]:
                pass

        client = APIClient(host_name="api-host")

        responses = list()
        async for resp in client.name_fetch():
            assert isinstance(resp, test_utils.MockResponse)
            responses.append(responses)

        assert len(responses) == 2

    @test_utils.mock_aiohttp(
        method="GET",
        resp=test_utils.MockResponse(status=201),
        req_validator=test_utils.RequestValidator(url="http://api-host/names"),
    )
    @pytest.mark.asyncio
    async def test_custom_hook_manipulate_resp(self, get_config: MockConfig = None):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=201, resp_schema=NameSchema())
            async def name_fetch(self, *, req: ClientRequest) -> NameID:
                pass

        def custom_hook(validator: RequestValidator, response: MockResponse):
            response.mock_json({"first": "Harry", "last": "Potter"})

        get_config.req_validator[0].custom_hook = custom_hook

        client = APIClient(host_name="api-host")

        name = await client.name_fetch()
        assert name.first == "Harry"
        assert name.last == "Potter"

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="POST",
        resp=MockResponse(201),
        req_validator=RequestValidator(
            content_type=MimeType.JSON, headers={"Content-Type": "application/json"}
        ),
    )
    async def test_mock_req_validate_data_type_w_schema(
        self, post_config: MockConfig = None
    ):
        test_name = Name("Harry", "Potter")

        def post_hook(validator: RequestValidator, resp: MockResponse):
            data = NameSchema().load(validator.req_data_decoded)
            assert data == test_name

            mock_data = NameSchema().dump(test_name)
            resp.mock_json(mock_data)

        post_config.req_validator[0].custom_hook = post_hook

        class APIClient(SpanClient):
            @handles.post(
                "/names",
                req_schema=NameSchema(),
                resp_codes=201,
                resp_schema=NameSchema(),
            )
            async def name_fetch(self, *, req: ClientRequest) -> NameID:
                req.media = Name("Harry", "Potter")

        client = APIClient(host_name="api-host")

        name = await client.name_fetch()
        print(name)

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(),
        req_validator=RequestValidator(url="http://api-host:8080/name"),
    )
    async def test_custom_port_url(self):
        class APIClient(SpanClient):
            @handles.get("/name")
            async def name_fetch(self, *, req: ClientRequest) -> None:
                pass

        client = APIClient(host_name="api-host", port=8080)
        _ = await client.name_fetch()

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(),
        req_validator=RequestValidator(url="http://api-host:8080/name"),
    )
    async def test_custom_default_port_url(self):
        class APIClient(SpanClient):
            DEFAULT_PORT = 8080

            @handles.get("/name")
            async def name_fetch(self, *, req: ClientRequest) -> None:
                pass

        client = APIClient(host_name="api-host")
        _ = await client.name_fetch()

    @test_utils.mock_aiohttp(
        method="GET",
        resp=test_utils.MockResponse(),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/endpoint",
            params={"project.field1": "1", "project.field2": "0"},
        ),
    )
    @pytest.mark.asyncio
    async def test_projection(self):
        class APIClient(SpanClient):
            @handles.get("/endpoint")
            async def name_fetch(self, *, req: ClientRequest):
                req.projection["field1"] = 1
                req.projection["field2"] = 0

        client = APIClient(host_name="api-host")

        await client.name_fetch()

    @test_utils.mock_aiohttp(
        method="GET",
        resp=test_utils.MockResponse(),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/endpoint",
            params={"project.field1": "0", "project.field2": "1"},
        ),
    )
    @pytest.mark.asyncio
    async def test_projection_from_user(self):
        class APIClient(SpanClient):
            @handles.get("/endpoint")
            async def name_fetch(
                self, projection: Dict[str, int], *, req: ClientRequest
            ):
                req.projection = projection

        client = APIClient(host_name="api-host")

        user_projection = {"field1": 0, "field2": 1}
        await client.name_fetch(user_projection)

    @test_utils.mock_aiohttp(
        method="GET",
        resp=test_utils.MockResponse(),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/endpoint",
            params={"project.field1": "1", "project.field2": "0",},
        ),
    )
    @pytest.mark.asyncio
    async def test_projection_validation_error(self):
        class APIClient(SpanClient):
            @handles.get("/endpoint")
            async def name_fetch(self, *, req: ClientRequest):
                req.projection["field1"] = 1

        client = APIClient(host_name="api-host")

        with pytest.raises(test_utils.ParamsMismatchError):
            await client.name_fetch()


class TestClientReqValidationErrors:
    UUID1 = uuid.uuid4()

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(200),
        req_validator=test_utils.RequestValidator(url=f"http://api-host/names/{UUID1}"),
    )
    async def test_url_mismatch(self):
        class APIClient(SpanClient):
            @handles.get("/names/{name_id}", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> NameID:
                req.path_params["name_id"] = "wrong_id"

        client = APIClient(host_name="api-host")

        with pytest.raises(test_utils.URLMismatchError):
            await client.name_fetch()

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(200),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names", params={"offset": 0}
        ),
    )
    async def test_params_key_missing(self):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> NameID:
                pass

        client = APIClient(host_name="api-host")

        with pytest.raises(test_utils.ParamsMismatchError):
            await client.name_fetch()

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(200),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names", params={"offset": 0}
        ),
    )
    async def test_params_value_wrong(self):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> NameID:
                req.query_params["offset"] = 10

        client = APIClient(host_name="api-host")

        with pytest.raises(test_utils.ParamsMismatchError):
            await client.name_fetch()

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(200),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names", headers={"Accept": "application/bson"}
        ),
    )
    async def test_headers_key_missing(self):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> NameID:
                pass

        client = APIClient(host_name="api-host")

        with pytest.raises(test_utils.HeadersMismatchError):
            await client.name_fetch()

    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(200),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names", headers={"Accept": "application/bson"}
        ),
    )
    @pytest.mark.asyncio
    async def test_headers_value_wrong(self):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> NameID:
                req.headers["Accept"] = "application/json"

        client = APIClient(host_name="api-host")

        with pytest.raises(test_utils.HeadersMismatchError):
            await client.name_fetch()

    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(200),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names", headers={"Accept": "application/bson"}
        ),
    )
    @pytest.mark.asyncio
    async def test_media_value_wrong(self):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> NameID:
                req.headers["Accept"] = "application/json"

        client = APIClient(host_name="api-host")

        with pytest.raises(test_utils.HeadersMismatchError):
            await client.name_fetch()

    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(200),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names", media={"first": "Harry", "last": "Potter"}
        ),
    )
    @pytest.mark.asyncio
    async def test_media_value_wrong(self):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> NameID:
                req.media = {"first": "Harry", "last": "Granger"}

        client = APIClient(host_name="api-host")

        with pytest.raises(test_utils.DataValidationError):
            await client.name_fetch()

    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(200),
        req_validator=test_utils.RequestValidator(
            url=f"http://api-host/names", custom_hook=validate_name_post
        ),
    )
    @pytest.mark.asyncio
    async def test_media_custom_validation_failure(self):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> NameID:
                req.media = {"first": "Harry", "last": "Granger"}

        client = APIClient(host_name="api-host")

        with pytest.raises(AssertionError):
            await client.name_fetch()

    @test_utils.mock_aiohttp(
        method="POST",
        resp=MockResponse(200),
        req_validator=test_utils.RequestValidator(
            headers={"Content-Type": MimeType.YAML.value}
        ),
    )
    @pytest.mark.asyncio
    async def test_media_type_validation_error(self):
        class APIClient(SpanClient):
            @handles.post("/names", mimetype_send=MimeType.YAML, resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> NameID:
                req.media = json.dumps({"first": "Harry", "last": "Granger"})

        client = APIClient(host_name="api-host")

        with pytest.raises(test_utils.DataTypeValidationError):
            await client.name_fetch()

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(),
        req_validator=test_utils.RequestValidator(url="http://api-host/names"),
    )
    async def test_mock_config_pass(self, *, get_config: MockConfig = None):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=201)
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                pass

        client = APIClient(host_name="api-host")
        get_config.resp[0].status = 201

        r = await client.name_fetch()
        assert r.status == 201

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=[MockResponse(200), MockResponse(201)],
        req_validator=[
            test_utils.RequestValidator(content_type=MimeType.JSON),
            test_utils.RequestValidator(content_type=MimeType.JSON),
        ],
    )
    async def test_mock_config_pass_validator(self, *, get_config: MockConfig = None):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=(200, 201))
            async def name_fetch(
                self, media, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                req.media = media

        client = APIClient(host_name="api-host")

        data1 = {"key": "value1"}
        data2 = {"key": "value2"}

        get_config.resp[0].mock_json(data1)
        get_config.resp[1].mock_json(data2)

        get_config.req_validator[0].media = data1
        get_config.req_validator[1].media = data2

        data_return = await client.name_fetch(data1)
        assert data_return == data1

        data_return = await client.name_fetch(data2)
        assert data_return == data2

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(method="GET", resp=MockResponse(200))
    @test_utils.mock_aiohttp(
        method="POST",
        resp=MockResponse(201),
        req_validator=RequestValidator(media={"first": "harry", "last": "potter"}),
    )
    async def test_mock_config_multiple(
        self, *, get_config: MockConfig = None, post_config: MockConfig = None
    ):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def name_fetch(self, *, req: ClientRequest) -> aiohttp.ClientResponse:
                pass

            @handles.post("/names", resp_codes=201)
            async def name_create(
                self, media, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                req.media = media

        client = APIClient(host_name="api-host")

        assert get_config.resp[0].status == 200
        assert post_config.resp[0].status == 201

        r = await client.name_fetch()
        print(r)
        assert r.status == 200

        r = await client.name_create({"first": "harry", "last": "potter"})
        print(r)
        assert r.status == 201

        await client.session.close()

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="POST", resp=MockResponse(200), req_validator=RequestValidator()
    )
    async def test_custom_handler(self, post_config: MockConfig = None):
        invoked_encode = dict(set=False)
        invoked_decode = dict(set=False)

        def csv_encode(data: List[dict]) -> bytes:
            invoked_encode["set"] = True

            encoded = io.StringIO()
            headers = list(data[0].keys())
            writer = csv.DictWriter(encoded, fieldnames=headers)
            writer.writeheader()
            writer.writerows(data)
            return encoded.getvalue().encode()

        def csv_decode(data: bytes) -> List[Dict[str, Any]]:
            invoked_decode["set"] = True

            csv_file = io.StringIO(data.decode())
            reader = csv.DictReader(csv_file)
            return [row for row in reader]

        class APIClient(SpanClient):
            register_mimetype("text/csv", encoder=csv_encode, decoder=csv_decode)

            @handles.post("/csv", mimetype_send="text/csv")
            async def csv_roundtrip(
                self, csv_data: List[Dict[str, Any]], *, req: ClientRequest
            ) -> List[Dict[str, Any]]:
                req.media = csv_data

        data = [{"key": "value1"}, {"key": "value2"}]

        post_config.req_validator[0].req_data = copy.copy(data)
        post_config.resp[0].content_type = "text/csv"
        post_config.resp[0].mock_content(csv_encode(data))

        client = APIClient(host_name="api-host")
        async with client:
            resp_data = await client.csv_roundtrip(data)
            assert data == resp_data

        assert invoked_decode["set"] is True
        assert invoked_encode["set"] is True
