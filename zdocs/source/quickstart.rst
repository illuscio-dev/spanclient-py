.. automodule:: spanclient

Quickstart
==========

All examples will be conducted on `mockable.io`_, a publicly available mock api creator.

Declare a Client
----------------

Clients are declared by subclassing the :class:`SpanClient` class.

.. code-block:: python

    from spanclient import SpanClient

    class HogwartsClient(SpanClient):
        DEFAULT_HOST_NAME =  "illuscio.mockable.io"
        DEFAULT_PROTOCOL = "https"

``DEFAULT_HOST_NAME`` does not need to be set, but will require the user to pass a value
for ``'hostname='`` to the init of ``HogwartsClient``.

``DEFAULT_PROTOCOL`` will be ``'http'`` if none is set.

Add a Method
------------

To add an endpoint method we decorate it with ``@handles.{method}``. Lets set up a
method for fetching text from an endpoint that returns the name of a hogwarts house for
us to be sorted into.

.. code-block:: python

    from spanclient import handles, ClientRequest
    from typing import List, Dict, Any

    REQ = SpanClient.REQ

    class HogwartsClient(SpanClient):
        DEFAULT_HOST_NAME =  "illuscio.mockable.io"
        DEFAULT_PROTOCOL = "https"

        @handles.get("/sortinghat")
        async def sort_house(self, req: ClientRequest=REQ) -> str:
            pass

That's all! The client is ready for use!

.. code-block:: python

    import asyncio

    # this is out main async function
    async def main():

        # declare our client
        client = HogwartsClient()

        # enter a context with our client. Upon exiting, the connection pool used by
        # aiohttp will be closed.
        async with client:
            # invoke our method
            house = await client.sort_house()
            # pretty-print the resulting loaded data.
            print("HOUSE:", house)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

Output: ::

    HOUSE: Ravenclaw

By default, the decoded response body is used as the return value of decorated
method.

The full url invoked in this example is
``'https://illuscio.mockable.io/sortinghat'``

.. note::

    ``{method}`` can be anything, but there are a few stubbed-out methods like
    ``.get()`` for IDE code completion. The actual decorator that is invoked is always
    ``handles.generic()``.

.. note::

    All methods must include a ``req`` keyword-only argument, which will be passed a
    :class:`ClientReq` by the decorator. To make it clear that this value does not need
    to be set by the end-user, a default value of SpanClient.REQ can be used. This value
    is not actually passed in, but replaced by a fresh :class:`ClientRequest` object
    each time the method is invoked.

Return Values
-------------

For most returns, no explicit handling of the response is required. All boilerplate is
handled by the decorator, and the return value is pulled from the decoded message body.

.. code-block:: python

    # biolerplate declaration of the client is removed in this and all subsequent
    # examples for clarity.

    @handles.get("/wizards")
    async def list_wizards(self, req: ClientRequest = REQ) -> List[Dict[str, Any]]:
        pass

Run it:

.. code-block:: python

    # all boilerplate for setting up and running the client in-context is removed here.
    # this code can be dropped into the first example above for testing.

    wizards = await client.list_wizards()
    print("WIZARDS:", json.dumps(wizards, indent=4), sep="\n")

Output: ::

    WIZARDS:
    [
        {
            "id": "eb340f70-524f-4459-a5ae-d7214f9780ca",
            "name": "Harry Potter",
            "house": "Gryffindor"
        },
        ...
        {
            "id": "05b289cc-9164-4b2d-ac23-badefbc9a4cd",
            "name": "Luna Lovegood",
            "house": "Ravenclaw"
        }
    ]

Check Response Code
-------------------

By default, responses are checked for 200 status code. To alter the expected response
code:

.. code-block:: python

    @handles.post("/house/gryffindor/point", resp_codes=201)
    async def one_point_to_gryffindor(self, req: ClientRequest = REQ) -> str:
        # adds 1 point to gryffindor
        pass

Run it:

.. code-block:: python

    points = await client.one_point_to_gryffindor()
    print("RESP:", resp)

Output: ::

    RESP: 542

If there are multiple acceptable codes:

.. code-block:: python

    @handles.post("/house/gryffindor/point", resp_codes=(200, 201, 202))
    async def one_point_to_gryffindor(self, req: ClientRequest = REQ) -> str:
        # adds 1 point to gryffindor
        pass


Handling Response / Return
--------------------------

Directly execute and handle a response:

.. code-block:: python

    @handles.post("/house/gryffindor/point", resp_codes=201)
    async def one_point_to_gryffindor(self, req: ClientRequest = REQ) -> int:
        # adds 1 point to gryffindor
        result: ResponseData = await req.execute()
        points = result.decoded
        return int(points)

We call :func:`ClientRequest.execute` to execute the request directly in the method.
This returns a :class:`ResponseData` object which we can use to determine a return.
In this case, we want to cast the points to an ``int``.

.. important::

    When :func:`ClientRequest.execute` is called inside a method, the return of the
    method is used as the return value of the method, unlike previous examples where the
    return value is pulled automatically from the response body.


Request Body
------------

The request body can be set via the ``ClientRequest.media`` attribute for unserialized
data or ``ClientRequest.content`` for serialized ``bytes`` data.

.. code-block:: python

    @handles.post("/wizards", resp_valid_codes=201,)
    async def add_wizard(self, wizard: dict, req: ClientRequest = REQ) -> str:
        # This endpoint assigns the house and wizard ID to a new student.
        req.media = wizard

Now when we call it:

.. code-block:: python

    wizard = {"name": "Cedric Diggory"}
    wizard = await client.add_wizard(wizard)
    print("ADDED:", wizard)

Output: ::

    ADDED:
    {
        "id": "30817cb1-4fd2-4f50-b258-4f225127f39c",
        "name": "Cedric Diggory",
        "house": "Hufflepuff"
    }

.. note::

    By default, ``list`` and ``dict`` objects are serialized as
    ``'application/json'``, and ``str`` objects are serialized as ``'text/plain'``

Content-Type Encoding
---------------------

:class:`SpanClient` natively handles the following http body mimetypes:

    - JSON (application/json)
    - YAML (application/yaml)
    - BSON (application/bson)
    - TEXT (text/plain)

Each of the supported mimetypes is represented as a string Enum in :class:`MimeType`.

.. code-block:: python

    from spanserver import MimeType,

    @handles.post("/wizards", mimetype_send=MimeType.YAML, resp_valid_codes=201,)
    async def add_wizard(
        self, wizard: dict, req: ClientRequest = REQ
    ) -> Dict[str, Any]:
        # This endpoint assigns the house and wizard ID to a new student.
        req.media = wizard

Now the request body will be encoded as yaml instead of json, and the ``'Content-Type'``
header will be set to ``'application/yaml'``

Content mime-type can also be set at the request level if it needs to be dynamically
determined:

.. code-block:: python

    @handles.post("/wizards", resp_valid_codes=201,)
    async def add_wizard(self, wizard: dict, req: ClientRequest = REQ) -> str:
        # This endpoint assigns the house and wizard ID to a new student.
        req.media = wizard
        req.mimetype_send=MimeType.YAML


Request a Content-Type
----------------------

Request a return mimetype from the server.

.. code-block:: python

    @handles.get("/wizards", mimetype_accept=MimeType.YAML)
    async def add_wizard(self, req: ClientRequest = REQ) -> Dict[str, Any]:
        pass

The ``'Accept'`` header will be set to ``'application/yaml'``, and services based on
`spanserver`_ will return yaml-encoded data.

Content-Type Sniffing
---------------------

When ``'Content-Type'`` is not specified in the response header, :class:`SpanClient`
will attempt to decode the content with every available decoder, until one does not
throw an error.

When registering custom encoders, make sure that they throw errors when they should.
For instance, json will decode raw strings to a str object, so the built-in json
decoder throws an error when the resulting object is not a dictionary or list.

Request body mimetype is resolved in the following order:

    1. Mimetype set to :func:`ClientRequest.mimetype_send`
    2. JSON for ``dict`` / ``list`` media values
    3. TEXT for ``str`` media.
    4. No action for ``bytes`` media values.

Content-Type Handlers
---------------------

Custom encoders and decoders can be registered with the api, and can replace the default
ones. Let's register a couple to handle text/csv content.

An encoder must take in a data object and turn it into bytes:

.. code-block:: python

    import csv
    import io
    from typing import List, Dict, Any


    def csv_encode(data: List[Dict[str, Any]]) -> bytes:
        encoded = io.StringIO()
        headers = list(data[0].keys())
        writer = csv.DictWriter(encoded, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)
        return encoded.getvalue().encode()

Decoders must take in bytes and return python objects.

.. code-block:: python

    def csv_decode(data: bytes) -> List[Dict[str, Any]]:
        csv_file = io.StringIO(data.decode())
        reader = csv.DictReader(csv_file)
        return [row for row in reader]


Now we can register them when declaring our client:

.. code-block:: python

    from spanclient import register_mimetype

    class APIClient(SpanClient):
        register_mimetype("text/csv", encoder=csv_encode, decoder=csv_decode)

        @handles.post("/csv", mimetype_send="text/csv")
        async def csv_roundtrip(
            self, csv_data: List[Dict[str, Any]], *, req: ClientRequest
        ) -> List[Dict[str, Any]]:
            req.media = csv_data

Path Parameters
---------------

Like `spanserver`_, spanclient allows f-string-like syntax for declaring path
parameters. Path parameters can be set via the :class:`ClientRequest`.

.. code-block:: python

    @handles.get("/wizard/{wizard_id}")
    async def fetch_wizard(
        self, wizard_id: uuid.UUID, req: ClientRequest = REQ
    ) -> Dict[str, Any]:
        req.path_params["wizard_id"] = wizard_id

Non-string params are cast via ``str()`` when being inserted into the url. Lets try it
out:

.. code-block:: python

    # Load our wizard id into a UUID object
    wizard_id = uuid.UUID("05b289cc-9164-4b2d-ac23-badefbc9a4cd")
    wizard = await client.fetch_wizard(wizard_id)

    # pretty-print the resulting loaded data.
    print("WIZARD:", json.dumps(wizard, indent=4))

Output ::

    WIZARD:
    {
        "id": "05b289cc-9164-4b2d-ac23-badefbc9a4cd",
        "name": "Luna Lovegood",
        "house": "Ravenclaw"
    }

The full url invoked in this example is
``'https://illuscio.mockable.io/wizard/05b289cc-9164-4b2d-ac23-badefbc9a4cd'``

Query Parameters
----------------

Query parameters are handled identically to path parameters.

.. code-block:: python

    @handles.get("/wizards")
    async def list_house(
        self, house: str, req: ClientRequest = REQ
    ) -> List[Dict[str, Any]]:
        req.query_params["house"] = house

We invoke it:

.. code-block::

    wizards = await client.list_house("Gryffindor")
    print("HOUSE GRYFFINDOR:", json.dumps(wizards, indent=4), sep="\n")

Output: ::

    HOUSE GRYFFINDOR:
    [
        {
            "id": "eb340f70-524f-4459-a5ae-d7214f9780ca",
            "name": "Harry Potter",
            "house": "Gryffindor"
        },
        {
            "id": "0a810fcb-75cd-4d40-be7e-0a3208ec05fd",
            "name": "Hermione Granger",
            "house": "Gryffindor"
        },
        {
            "id": "230173db-dfaa-4296-a8e6-510aabe34ecb",
            "name": "Ron Weasley",
            "house": "Gryffindor"
        }
    ]

The full url invoked in this example is
``'http://illuscio.mockable.io/wizards%3Fhouse=Gryffindor'``

You can also set query params on the method decorator. These will be added every time
the method is invoked:

.. code-block:: python

    @handles.get("/wizards", query_params={"house": "Gryffindor"})
    async def list_gryffindor(self, req: ClientRequest = REQ) -> str:
        pass

Which would be called for the same result:

.. code-block:: python

    wizards = await client.list_gryffindor()


Projection URL Params
---------------------

Natively handle `SpanServer's projection convention`_ for slimming down response
payloads.

.. code-block:: python

    @handles.get("/wizards")
    async def list_wizards(
        self, req: ClientRequest = REQ
    ) -> List[Dict[str, Any]]:
        req.projection["house"] = 0

When invoked, the ``'house'`` field will be suppressed:

.. code-block:: python

    wizards = await client.list_wizards()
    # pretty-print the resulting loaded data.
    print("WIZARDS:", json.dumps(wizards, indent=4), sep="\n")

Output: ::

    WIZARDS:
    [
        {
            "id": "eb340f70-524f-4459-a5ae-d7214f9780ca",
            "name": "Harry Potter"
        },
        {
            "id": "0a810fcb-75cd-4d40-be7e-0a3208ec05fd",
            "name": "Hermione Granger"
        },
        {
            "id": "230173db-dfaa-4296-a8e6-510aabe34ecb",
            "name": "Ron Weasley"
        },
        {
            "id": "245dca2d-1c72-495e-99a8-08c2808325b8",
            "name": "Draco Malfoy"
        },
        {
            "id": "30817cb1-4fd2-4f50-b258-4f225127f39c",
            "name": "Cedric Diggory"
        },
        {
            "id": "05b289cc-9164-4b2d-ac23-badefbc9a4cd",
            "name": "Luna Lovegood"
        }
    ]

Use the same method to allow users to define their own projection:

.. code-block:: python

    @handles.get("/wizards")
    async def list_wizards(
        self,
        projection: Optional[Dict[str, int]] = None,
        req: ClientRequest = REQ
    ) -> List[Dict[str, Any]]:
        if projection is not None:
            req.projection = projection

Invoke it:

.. code-block:: python

    projection = {"name": 1}
    wizards = await client.list_wizards(projection)

    print("WIZARDS:", json.dumps(wizards, indent=4), sep="\n")

Output: ::

    WIZARDS:
    [
        {
            "name": "Harry Potter"
        },
        {
            "name": "Hermione Granger"
        },
        {
            "name": "Ron Weasley"
        },
        {
            "name": "Draco Malfoy"
        },
        {
            "name": "Cedric Diggory"
        },
        {
            "name": "Luna Lovegood"
        }
    ]


Request Headers
---------------

Headers are handled identically to path and query params. Either:

.. code-block:: python

    @handles.get("/wizards")
    async def fetch_wizards(self, some_value: str, req: ClientRequest = REQ) -> str:
        req.headers["some-header"] = some_value

Or:

.. code-block:: python

    @handles.get("/wizards", headers={"some-header": "some-value"})
    async def fetch_wizards(self, req: ClientRequest = REQ) -> str:
        pass


Request Body Schema
--------------------

Let's make a marshmallow schema for our wizard info:

.. code-block:: python

    class WizardSchema(marshmallow.Schema):
        id = marshmallow.fields.UUID()
        name = marshmallow.fields.Str()
        house = marshmallow.fields.Str()

        @marshmallow.validates("house")
        def is_valid_house(self, value: str, **kwargs: Any):
            houses = ["Gryffindor", "Slytherin", "Hufflepuff", "Ravenclaw"]
            if value not in houses:
                raise marshmallow.ValidationError(
                    f"{value} is not a hogwarts house"
                )

We can use this schema to serialize our request body:

.. code-block:: python

    @handles.post(
        "/wizards", req_schema=WizardSchema(only=["name"]), resp_valid_codes=201
    )
    async def add_wizard(self, wizard: dict, req: ClientRequest = REQ) -> str:
        # This endpoint assigns the house and wizard ID. We
        req.media = wizard

When we invoke it:

.. code-block:: python

    wizard = {"name": "Cedric Diggory"}
    wizard = await client.add_wizard(wizard)
    print("ADDED:", json.dumps(wizard, indent=4), sep="\n")

Output ::

    ADDED:
    {
        "id": "30817cb1-4fd2-4f50-b258-4f225127f39c",
        "name": "Cedric Diggory",
        "house": "Hufflepuff"
    }

Response Body Schema
--------------------

In the last example, the uuid came back as a string. We can register a response body
schema to load it when the response is returned.

.. code-block:: python

    @handles.post(
        "/wizards",
        req_schema=WizardSchema(only=["name"]),
        resp_valid_codes=201,
        resp_schema=WizardSchema()
    )
    async def add_wizard(self, wizard: dict, req: ClientRequest = REQ) -> str:
        # This endpoint assigns the house and wizard ID to a new student.
        req.media = wizard

Now when we call it:

.. code-block:: python

    wizard = {"name": "Cedric Diggory"}
    wizard = await client.add_wizard(wizard)
    print("ADDED:", wizard)

Output: ::

    ADDED: {... 'id': UUID('30817cb1-4fd2-4f50-b258-4f225127f39c')...}

The uuid object has been deserialized.

.. note::

    For those who wish to deserialize from and serialize to `dataclasses`_, there is a
    sister project, `Grahamcracker`_, specifically written for use with the `spanreed`_
    family.

Update Data In-Place
--------------------

In the above example, the method returns a NEW data object when the wizard is posted,
but we can update objects IN-PLACE if we want:

.. code-block:: python

    @handles.post(
        "/wizards",
        req_schema=WizardSchema(only=["name"]),
        resp_valid_codes=201,
        resp_schema=WizardSchema()
    )
    async def add_wizard(self, wizard: dict, req: ClientRequest = REQ) -> str:
        # This endpoint assigns the house and wizard ID. We
        req.media = wizard
        req.update_obj = wizard

Run it:

.. code-block::

    wizard = {"name": "Cedric Diggory"}
    # wizard is updated in-place
    await client.add_wizard(wizard)
    print("ADDED:", wizard)

Output: ::

    ADDED: {'name': 'Cedric Diggory', 'id': ..., 'house': 'Hufflepuff'}

.. note::

    SpanClient uses a library called `Gemma`_ to automatically update objects in-place.
    However, there are a few limitations to it's capabilities:

        - The Structure of the existing and incoming objects must be the same: for
          instance key1.nested1 must exist on both objects.
        - It does not matter if the "addresses" are attributes or keys, both are
          discoverable, so a dataclass can be updated by a dict, as long as their field
          names are identical.
        - Nested objects like dicts or dataclasses are updated in-place.
        - Nested sequences are wholly replaced. If your data has a list of sub-data,
          the list is not updated in-place, it is replaced with a new list.

Assign a custom updater if something more complicated is needed:

.. code-block:: python

    def update_wizard(current: dict, new: dict) -> None:
        current["id"] = new["id"]
        current["house"] = new["house"]

    @handles.post(
        "/wizards",
        req_schema=WizardSchema(only=["name"]),
        resp_valid_codes=201,
        resp_schema=WizardSchema(),
        data_updater=update_wizard
    )
    async def add_wizard(self, wizard: dict, req: ClientRequest = REQ) -> str:
        # This endpoint assigns the house and wizard ID. We
        req.media = wizard
        req.update_obj = wizard

Response Errors
---------------

When we get a response code we were not expecting, a generic
:class:`StatusMismatchError` is returned.

Spanclient is designed to work seamlessly with `spanserver`_ and understands
it' error conventions. Errors returned in response headers that conform to the
`spanreed`_ spec will be raised as native errors.

.. code-block:: python

    @handles.get("/wizards/slytherin/good")
    async def good_slytherins(self, req: ClientRequest = REQ) -> List[Dict[str, Any]]:
        pass

Run it:

.. code-block:: python

    wizards = await client.good_slytherins()

Output: ::

    Traceback (most recent call last):
        ...
    spantools.errors_api._classes.NothingToReturnError: There are no good Slytherins.

Register custom errors while declaring your client by subclassing
:class:`errors_api.APIError`, and assigning expected HTTP and api error codes.

.. code-block:: python

    class BrokenWandError(errors_api.APIError):
        http_code: int = 404
        api_code: int = 2001

    class HogwartsClient(SpanClient):
        DEFAULT_HOST_NAME = "illuscio.mockable.io"
        DEFAULT_PROTOCOL = "https"

        API_ERRORS_ADDITIONAL = [BrokenWandError]

        @handles.post("/spell")
        async def cast_spell(self, req: ClientRequest = REQ) -> List[Dict[str, Any]]:
            pass

.. note::

    If you are writing both a client and backend together, have a single python package
    with errors and schemas for the API that is used by both the server and client.

    In the case of spanclient and `spanserver`_, both use the same error classes from
    a shared package called `spantools`_.

    This strategy ensures that when tweaks occur to an error's definition, it only has
    to be updated in one place (at least for the python libraries).

Paged Endpoints
---------------

Like with errors, :class:`SpanClient` offers an easy way to deal with paged endpoints
using `spanserver's paging convention`_

.. code-block:: python

    @handles.paged(limit=2)
    @handles.get("/wizards")
    async def list_wizards(self, req: ClientRequest = REQ) -> List[Dict[str, Any]]:
        pass

``limit=2`` sets the ``'paging-limit'`` query parameter to ``'2'``, so the server will
return our data two us in batches of two wizards per request.

Run it:

.. code-block::

    async for wizard in client.list_wizards():
        print("WIZARD:", wizard)

Output: ::

    WIZARD: {'id': ..., 'name': 'Harry Potter', 'house': 'Gryffindor'}
    WIZARD: {'id': ..., 'name': 'Hermione Granger', 'house': 'Gryffindor'}
    WIZARD: {'id': ..., 'name': 'Ron Weasley', 'house': 'Gryffindor'}
    WIZARD: {'id': ..., 'name': 'Draco Malfoy', 'house': 'Slytherin'}
    WIZARD: {'id': ..., 'name': 'Cedric Diggory', 'house': 'Hufflepuff'}
    WIZARD: {'id': ..., 'name': 'Luna Lovegood', 'house': 'Ravenclaw'}

Our method has been turned into an async iterable! The paging happens seamlessly in the
background, so even though our wizards are being fetched in groups of two, we get all
six when iterating through them:

Paging limit and starting offset can also be set on the request object:

.. code-block:: python

    @handles.paged()
    @handles.get("/wizards")
    async def list_wizards(
        self, skip: int, batch_size: int, *, req: ClientRequest = REQ
    ) -> List[Dict[str, Any]]:
        req.paging.offset_start = skip
        req.paging.limit = batch_size


.. _mockable.io: https://www.mockable.io/swagger/index.html?url=https%3A%2F%2Filluscio.mockable.io%3Fopenapi#/illuscio
.. _spanserver: https://illuscio-dev-spanreed-py.readthedocs-hosted.com/en/latest/
.. _Gemma: https://illuscio-dev-gemma-py.readthedocs-hosted.com/en/latest/
.. _spanserver's paging convention: https://illuscio-dev-spanreed-py.readthedocs-hosted.com/en/latest/quickstart.html#paging
.. _dataclasses: https://docs.python.org/3/library/dataclasses.html
.. _Grahamcracker: https://illuscio-dev-grahamcracker-py.readthedocs-hosted.com/en/latest/
.. _spantools: https://illuscio-dev-spantools-py.readthedocs-hosted.com/en/latest/
