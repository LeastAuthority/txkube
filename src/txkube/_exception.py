# Copyright Least Authority Enterprises.
# See LICENSE for details.

from json import loads

from twisted.web.http import NOT_FOUND, CONFLICT
from twisted.web.client import readBody


def _full_kind(details):
    """
    Determine the full kind (including a group if applicable) for some failure
    details.

    :see: ``v1.Status.details``
    """
    kind = details[u"kind"]
    if details.get(u"group") is not None:
        kind += u"." + details[u"group"]
    return kind



class KubernetesError(Exception):
    """
    Kubernetes has returned an error for some attempted operation.

    :ivar int code: The HTTP response code.
    :ivar Status status: The *v1.Status* returned in the response.
    """
    def __init__(self, code, status):
        self.code = code
        self.status = status

    def __cmp__(self, other):
        if isinstance(other, self.__class__):
            return cmp((self.code, self.status), (other.code, other.status))
        return NotImplemented

    @classmethod
    def not_found(cls, details):
        # Circular imports :(  See below.
        from ._model import v1
        kind = _full_kind(details)
        return cls(
            NOT_FOUND,
            v1.Status(
                status=u"Failure",
                message=u'{kind} "{name}" not found'.format(
                    kind=kind, name=details[u"name"],
                ),
                reason=u"NotFound",
                details=details,
                metadata={},
                code=NOT_FOUND,
            ),
        )

    @classmethod
    def already_exists(cls, details):
        # Circular imports :(  See below.
        from ._model import v1
        kind = _full_kind(details)
        return cls(
            CONFLICT,
            v1.Status(
                status=u"Failure",
                message=u'{kind} "{name}" already exists'.format(
                    kind=kind, name=details[u"name"],
                ),
                reason=u"AlreadyExists",
                details=details,
                metadata={},
                code=CONFLICT,
            ),
        )

    @classmethod
    def object_modified(cls, details):
        from ._model import v1
        kind = _full_kind(details)
        fmt = (
            u'Operation cannot be fulfilled on {kind} "{name}": '
            u'the object has been modified; '
            u'please apply your changes to the latest version and try again'
        )
        return cls(
            CONFLICT,
            v1.Status(
                code=CONFLICT,
                details=details,
                message=fmt.format(kind=kind, name=details[u"name"]),
                metadata={},
                reason=u'Conflict',
                status=u'Failure',
            ),
        )


    @classmethod
    def from_response(cls, response):
        """
        Create a ``KubernetesError`` for the given error response from a
        Kubernetes server.

        :param twisted.web.iweb.IResponse response: The response to inspect
            for the error details.

        :return Deferred(KubernetesError): The error with details attached.
        """
        # txkube -> _exception -> _model -> txkube :(
        #
        # Stick the import here to break the cycle.
        #
        # This is usually what happens with the expose-it-through-__init__
        # style, I guess.
        #
        # Can probably deprecate this method, anyhow, and make people use
        # from_model_and_response instead.
        from ._model import v1_5_model
        return cls.from_model_and_response(v1_5_model, response)


    @classmethod
    def from_model_and_response(cls, model, response):
        """
        Create a ``KubernetesError`` for the given error response from a
        Kubernetes server.

        :param model: The Kubernetes data model to use to convert the server
            response into a Python object.

        :param twisted.web.iweb.IResponse response: The response to inspect
            for the error details.

        :return Deferred(KubernetesError): The error with details attached.
        """
        d = readBody(response)
        d.addCallback(
            lambda body: cls(
                response.code,
                model.iobject_from_raw(loads(body)),
            ),
        )
        return d



    def __repr__(self):
        return "<KubernetesError: code = {}; status = {}>".format(
            self.code, self.status,
        )

    __str__ = __repr__



class UnrecognizedVersion(ValueError):
    """
    An object *apiVersion* was encountered that we don't know about.

    :ivar unicode apiVersion: The API version encountered.
    :ivar object obj: The whole marshalled object.
    """
    def __init__(self, apiVersion, obj):
        ValueError.__init__(self, apiVersion)
        self.apiVersion = apiVersion
        self.obj = obj



class UnrecognizedKind(ValueError):
    """
    An object *kind* was encountered that we don't know about.

    :ivar unicode apiVersion: The API version encountered.
    :ivar unicode kind: The object kind encountered.
    :ivar object obj: The whole marshalled object.
    """
    def __init__(self, apiVersion, kind, obj):
        ValueError.__init__(self, apiVersion, kind)
        self.apiVersion = apiVersion
        self.kind = kind
        self.obj = obj
