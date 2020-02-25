.. automodule:: spanclient

API Guide
=========

SpanClient
----------

.. autoclass:: SpanClient
    :special-members: __init__
    :members:

.. autoclass:: spanclient._endpoint_wrapper.EndpointWrapper
    :members:

ClientRequest
-------------

.. autoclass:: ClientRequest
    :members:

.. autoclass:: PagingReqClient
    :members:

MimeType
--------

.. autoclass:: MimeType
   :members:

   Enum class for the default supported Content-Types / Mimetypes for decoding and
   encoding.

   =========== ======================
   Enum Attr   Text Value
   =========== ======================
   JSON        application/json
   YAML        application/yaml
   BSON        application/bson
   TEXT        text/plain
   =========== ======================

   .. automethod:: is_mimetype

   .. automethod:: from_name

   .. automethod:: to_string

   .. automethod:: add_to_headers

   .. automethod:: from_headers

.. data:: MimeTypeTolerant

   Typing alias for ``Union[MimeType, str, None]``.

Errors
------

.. autoexception:: StatusMismatchError

.. autoexception:: ContentTypeUnknownError

.. autoexception:: ContentEncodeError

.. autoexception:: ContentDecodeError


API Errors
----------

Default `spanserver`_ api errors. Found in the ``errors_api`` sub-module.

.. autoexception:: spanclient.errors_api.APIError

.. autoexception:: spanclient.errors_api.InvalidMethodError

.. autoexception:: spanclient.errors_api.NothingToReturnError

.. autoexception:: spanclient.errors_api.RequestValidationError

.. autoexception:: spanclient.errors_api.APILimitError

.. autoexception:: spanclient.errors_api.ResponseValidationError


Testing Utilities
-----------------

For use with `pytest`_ and `pytest-asyncio`_. Found in the ``test_utils`` sub-module.

.. autofunction:: spanclient.test_utils.mock_aiohttp

.. autoclass:: spanclient.test_utils.MockResponse
    :members:

.. autoclass:: spanclient.test_utils.RequestValidator
    :members:

.. autoclass:: spanclient.test_utils.MockConfig
    :members:

Testing Errors
--------------

.. autoexception:: spanclient.test_utils.ResponseValidationError

.. autoexception:: spanclient.test_utils.DataTypeValidationError

.. autoexception:: spanclient.test_utils.DataValidationError

.. autoexception:: spanclient.test_utils.URLMismatchError

.. autoexception:: spanclient.test_utils.ParamsMismatchError

.. autoexception:: spanclient.test_utils.TextValidationError

.. autoexception:: spanclient.test_utils.WrongExceptionError

.. autoexception:: spanclient.test_utils.PagingMismatchError

.. autoexception:: spanclient.test_utils.HeadersMismatchError

.. _spanserver: https://illuscio-dev-spanreed-py.readthedocs-hosted.com/en/latest/
.. _pytest-asyncio: https://github.com/pytest-dev/pytest-asyncio
.. _pytest: https://docs.pytest.org/en/latest/
