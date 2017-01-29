# Copyright Least Authority Enterprises.
# See LICENSE for details.


class KubernetesError(Exception):
    def __init__(self, code, response):
        self.code = code
        self.response = response


    def __repr__(self):
        return "<KubernetesError: code = {}; response = {}>".format(
            self.code, self.response,
        )

    __str__ = __repr__
