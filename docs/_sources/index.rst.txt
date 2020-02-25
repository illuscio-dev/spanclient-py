.. islelib documentation master file, created by
   sphinx-quickstart on Mon Oct  1 00:18:03 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. automodule:: spanclient

SpanClient
==========

Many frameworks exist for quickly declaring REST-ful API's, but few exist for quickly
declaring clients to consume them.

A good, pre-built client to make interacting with your API painless goes a long way
toward your API's usability. SpanClient seeks to make declaring a high-level client as
painless as declaring the services that feed it.

Lets declare a small client can interact with an API that stores names of people. We
need to make two methods: one that fetches a name based on a UUID, and one that posts
a new name to be assigned a uuid:

.. code-block:: python

   import uuid
   import marshmallow
   from spanclient import SpanClient, handles, MimeType, ClientRequest


   class NameSchema(marshmallow.Schema):
       id = marshmallow.fields.UUID()
       first = marshmallow.fields.Str()
       last = marshmallow.fields.Str()

   REQ = SpanClient.REQ

   class MyClient(SpanClient):
       DEFAULT_HOST_NAME = "api.names.com"
       DEFAULT_PROTOCOL = "https"

       @handles.get(
           "/names/{name_id}",
           resp_schema=NameSchema()
       )
       async def fetch_name(self, name_id: uuid.UUID, req: ClientRequest=REQ) -> dict:
           req.path_params["name_id"] = name_id

       @handles.post(
           "/names",
           mimetype_send=MimeType.YAML,
           req_schema=NameSchema(exclude=["id"]),
           mimetype_accept=MimeType.YAML,
           resp_codes=201,
           resp_schema=NameSchema()
       )
       async def create_name(self, name: dict, req: ClientRequest=REQ) -> dict:
           req.update_obj = name


   client = MyClient()

That's all it takes!

The first method:

   - Fetches name objects from "www.names.api/names/{name_id}"
   - Uses the passed ``name_id`` value for the ``{name_id}`` url path param
   - Loads the response body using ``NameSchema()``
   - Automatically use the loaded response body as the method's return value.

The second method:

   - Takes in a name object and uses ``NameSchema(exclude=["id"])`` to
     serialize the request body as YAML data.
   - Requests YAML data back from the server.
   - Deserialized the response body using ``NameSchema()``.
   - Checks that the response code is ``201``.
   - Update the existing ``name`` object in-place with the returned data rather than
     returning a new one.
   - Use the existing name object as the method's return value.

Both Methods:

   - Will raise errors sent back from the server using native python exceptions.
   - Send requests asynchronously using `asyncio`_.

.. important::

   SpanClient is designed to work with `SpanServer`_, and follows it's conventions
   for passing errors, paging, and encoding content.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   ./quickstart.rst
   ./test_utilities.rst
   ./api_guide.rst

.. _asyncio: https://docs.python.org/3/library/asyncio.html
.. _SpanServer: https://illuscio-dev-spanreed-py.readthedocs-hosted.com/en/latest/
