Test Utilities
==============

Testing http clients can be a tedious process, as http responses must be mocked.
The ``test_util`` sub-package offers some testing utilities for mocking aiohttp
responses.

.. note::

    All examples below make use of the `pytest-asyncio`_ plugin for natively handling
    async tests.

Patch an aiohttp Method
-----------------------

We can patch an aiohttp method by using :func:`spanclient.test_utils.mock_aiohttp`,
and supply :class:`spanclient.test_utils.MockResponse` objects to be returned when
the relevant aiohttp method is invoked.

.. code-block:: python

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(method="GET", resp=MockResponse(200))
    async def test_mock_config_multiple():

        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def send_200(
                self, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                pass

        client = APIClient(host_name="api-host")

        async with client:
            await client.send_200()
            await client.send_200()
            await client.send_200()

Mock responses are returned endlessly, so all calls above will succeed.

Mock Response Bodies
--------------------

.. code-block:: python

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(200, _json={"first": "Harry", "last": "Potter"})
    )
    async def test_mock_config_multiple():

        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def name_fetch(
                self, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                pass

        client = APIClient(host_name="api-host")

        async with client:
            name = await client.name_fetch()
            assert name == {"first": "Harry", "last": "Potter"}

The ``'Content-Type'`` header is mocked automatically when using _json, _yaml, or _bson.

Mock Response Headers
---------------------

.. code-block:: python

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=MockResponse(200, headers={"some-header": "some-value"})
    )
    async def test_mock_config_multiple():

        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def send_200(
                self, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                pass

        client = APIClient(host_name="api-host")

        async with client:
            await client.send_200()
            await client.send_200()
            await client.send_200()


Mock Multiple Responses
-----------------------

.. code-block:: python

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=[
            MockResponse(200, _json={"first": "Harry", "last": "Potter"}),
            MockResponse(200, _json={"first": "Hermione", "last": "Granger"}),
        ]
    )
    async def test_mock_config_multiple():

        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def name_fetch(
                self, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                pass

        client = APIClient(host_name="api-host")

        async with client:
            name = await client.name_fetch()
            assert name == {"first": "Harry", "last": "Potter"}

            name = await client.name_fetch()
            assert name == {"first": "Hermione", "last": "Granger"}

            name = await client.name_fetch()
            assert name == {"first": "Harry", "last": "Potter"}

            name = await client.name_fetch()
            assert name == {"first": "Hermione", "last": "Granger"}

When multiple responses are specified, they will be yielded in order, then repeated.

Mock Multiple Methods
---------------------

.. code-block:: python

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(method="POST", resp=MockResponse(201))
    @test_utils.mock_aiohttp(method="GET", resp=MockResponse(200))
    async def test_mock_config_multiple():

        class APIClient(SpanClient):
            @handles.get("/test", resp_codes=200)
            async def send_200(
                self, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                pass

            @handles.post("/test", resp_codes=201)
            async def post_201(
                self, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                pass

        client = APIClient(host_name="api-host")
        async with client:
            await client.send_200()
            await client.send_200()
            await client.send_200()

            await client.post_201()
            await client.post_201()
            await client.post_201()

Validate Requests
-----------------

Use :class:`spanclient.test_utils.RequestValidator` to validate the values passed into
aiohttp methods.

.. code-block:: python

    VALIDATOR_TRIGGERED = dict(set=False)

    def validate_name_post(validator: RequestValidator, response: MockResponse):
        global VALIDATOR_TRIGGERED
        VALIDATOR_TRIGGERED["set"] = True

        assert validator.req_data_decoded == NameSchema().dump(
            {"first": "Harry", "last": "Potter"}
        )

    @pytest.mark.asyncio
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
    async def test_req_validation_client():

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

        async with client:

            assert TestSpanClient.VALIDATOR_TRIGGERED is False

            name = await client.name_fetch(TestSpanClient.UUID1)
            assert name.id == TestSpanClient.UUID1
            assert name.first == "Harry"
            assert name.last == "Potter"

            assert VALIDATOR_TRIGGERED["set"] is True

Just like responses, multiple validation requests can be set which will be endlessly
iterated through.

Configure Mocks
---------------

:class:`spanclient.test_utils.MockConfig` instances will be passed into and
``{method}_config = None`` params of the test for configuration during runtime.

.. code-block:: python

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(
        method="GET",
        resp=[MockResponse(200), MockResponse(201)],
        req_validator=[
            test_utils.RequestValidator(content_type=MimeType.JSON),
            test_utils.RequestValidator(content_type=MimeType.JSON),
        ],
    )
    async def test_mock_config_pass_validator(get_config: MockConfig = None):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=(200, 201))
            async def name_fetch(
                self, media, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                req.media = media

        client = APIClient(host_name="api-host")

        async with client:

            data1 = {"key": "value1"}
            data2 = {"key": "value2"}

            get_config.response[0].mock_json(data1)
            get_config.response[1].mock_json(data2)

            get_config.req_validator[0].media = data1
            get_config.req_validator[1].media = data2

            data_return = await client.name_fetch(data1)
            assert data_return == data1

            data_return = await client.name_fetch(data2)
            assert data_return == data2

One config is passed per method:

.. code-block:: python

    @pytest.mark.asyncio
    @test_utils.mock_aiohttp(method="GET", resp=MockResponse(200))
    @test_utils.mock_aiohttp(
        method="POST",
        resp=MockResponse(201),
        req_validator=RequestValidator(),
    )
    async def test_mock_config_multiple(
        self, *, get_config: MockConfig = None, post_config: MockConfig = None
    ):
        class APIClient(SpanClient):
            @handles.get("/names", resp_codes=200)
            async def name_fetch(
                self, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                pass

            @handles.post("/names", resp_codes=201)
            async def name_create(
                self, media, *, req: ClientRequest
            ) -> aiohttp.ClientResponse:
                req.media = media

        client = APIClient(host_name="api-host")
        name_data= {"first": "harry", "last": "potter"}

        async with client:

            get_config.response[0].media == name_data

            post_config.response[0].media = name_data
            post_config.req_validator[0].media = name_data

            name = await client.name_fetch()
            assert name == name_data

            name = await client.name_create()
            assert name == name_data

.. important::

    :class:`MockConfig` parameters must have a default value or pytest will interpret
    them as expected `fixtures`_ for the given test.

    None is not a required value for the default, but it is a convenient one.

.. _fixtures: https://docs.pytest.org/en/latest/fixture.html
.. _pytest-asyncio: https://github.com/pytest-dev/pytest-asyncio
