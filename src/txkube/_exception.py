# Copyright Least Authority Enterprises.
# See LICENSE for details.

from json import loads

from twisted.web.client import readBody


class KubernetesError(Exception):
    """
    Kubernetes has returned an error for some attempted operation.

    :ivar int code: The HTTP response code.
    :ivar Status status: The *v1.Status* returned in the response.
    """
    def __init__(self, code, status):
        self.code = code
        self.status = status


    @classmethod
    def from_response(cls, response):
        """
        Create a ``KubernetesError`` for the given error response from a
        Kubernetes server.

        :param twisted.web.iweb.IResponse response: The response to inspect
            for the error details.

        :return Deferred(KubernetesError): The error with details attached.
        """
        d = readBody(response)
        # txkube -> _exception -> _model -> txkube :(
        #
        # Stick the import here to break the cycle.
        #
        # This is usually what happens with the expose-it-through-__init__
        # style, I guess.
        from ._model import iobject_from_raw
        d.addCallback(lambda body: cls(response.code, iobject_from_raw(loads(body))))
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
