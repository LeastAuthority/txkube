# Copyright Least Authority Enterprises.
# See LICENSE for details.

from json import loads

from twisted.web.client import readBody


class KubernetesError(Exception):
    def __init__(self, code, response):
        self.code = code
        self.response = response


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
        from ._model import Status
        d.addCallback(lambda body: cls(response.code, Status.create(loads(body))))
        return d


    def __repr__(self):
        return "<KubernetesError: code = {}; response = {}>".format(
            self.code, self.response,
        )

    __str__ = __repr__
