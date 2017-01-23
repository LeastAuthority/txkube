# Copyright Least Authority Enterprises.
# See LICENSE for details.

import os

from uuid import uuid4

from fixtures import TempDir

from testtools.matchers import Equals, Contains

from twisted.python.filepath import FilePath
from twisted.internet.protocol import Factory
from twisted.web.http_headers import Headers
from twisted.test.iosim import ConnectionCompleter
from twisted.test.proto_helpers import AccumulatingProtocol, MemoryReactor

from ..testing import TestCase

from .. import authenticate_with_serviceaccount

# Just an arbitrary certificate pulled off the internet.  Details ought not
# matter.
_CA_CERT_PEM = b"""\
-----BEGIN CERTIFICATE-----
MIIDfTCCAuagAwIBAgIDErvmMA0GCSqGSIb3DQEBBQUAME4xCzAJBgNVBAYTAlVT
MRAwDgYDVQQKEwdFcXVpZmF4MS0wKwYDVQQLEyRFcXVpZmF4IFNlY3VyZSBDZXJ0
aWZpY2F0ZSBBdXRob3JpdHkwHhcNMDIwNTIxMDQwMDAwWhcNMTgwODIxMDQwMDAw
WjBCMQswCQYDVQQGEwJVUzEWMBQGA1UEChMNR2VvVHJ1c3QgSW5jLjEbMBkGA1UE
AxMSR2VvVHJ1c3QgR2xvYmFsIENBMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB
CgKCAQEA2swYYzD99BcjGlZ+W988bDjkcbd4kdS8odhM+KhDtgPpTSEHCIjaWC9m
OSm9BXiLnTjoBbdqfnGk5sRgprDvgOSJKA+eJdbtg/OtppHHmMlCGDUUna2YRpIu
T8rxh0PBFpVXLVDviS2Aelet8u5fa9IAjbkU+BQVNdnARqN7csiRv8lVK83Qlz6c
JmTM386DGXHKTubU1XupGc1V3sjs0l44U+VcT4wt/lAjNvxm5suOpDkZALeVAjmR
Cw7+OC7RHQWa9k0+bw8HHa8sHo9gOeL6NlMTOdReJivbPagUvTLrGAMoUgRx5asz
PeE4uwc2hGKceeoWMPRfwCvocWvk+QIDAQABo4HwMIHtMB8GA1UdIwQYMBaAFEjm
aPkr0rKV10fYIyAQTzOYkJ/UMB0GA1UdDgQWBBTAephojYn7qwVkDBF9qn1luMrM
TjAPBgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwIBBjA6BgNVHR8EMzAxMC+g
LaArhilodHRwOi8vY3JsLmdlb3RydXN0LmNvbS9jcmxzL3NlY3VyZWNhLmNybDBO
BgNVHSAERzBFMEMGBFUdIAAwOzA5BggrBgEFBQcCARYtaHR0cHM6Ly93d3cuZ2Vv
dHJ1c3QuY29tL3Jlc291cmNlcy9yZXBvc2l0b3J5MA0GCSqGSIb3DQEBBQUAA4GB
AHbhEm5OSxYShjAGsoEIz/AIx8dxfmbuwu3UOx//8PDITtZDOLC5MH0Y0FWDomrL
NhGc6Ehmo21/uBPUR/6LWlxz/K7ZGzIZOKuXNBSqltLroxwUCEm2u+WR74M26x1W
b8ravHNjkOR/ez4iyz0H7V84dJzjA1BOoa+Y7mHyhD8S
-----END CERTIFICATE-----
"""

class AuthenticateWithServiceAccountTests(TestCase):
    """
    Tests for ``authenticate_with_serviceaccount``.
    """
    def _authorized_request(self, token, headers):
        """
        Get an agent using ``authenticate_with_serviceaccount`` and issue a
        request with it.

        :return bytes: The bytes of the request the agent issues.
        """
        server = AccumulatingProtocol()
        factory = Factory.forProtocol(lambda: server)
        factory.protocolConnectionMade = None

        reactor = MemoryReactor()
        reactor.listenTCP(80, factory)

        t = FilePath(self.useFixture(TempDir()).join(b""))
        serviceaccount = t.child(b"serviceaccount")
        serviceaccount.makedirs()

        serviceaccount.child(b"ca.crt").setContent(_CA_CERT_PEM)
        serviceaccount.child(b"token").setContent(token)

        self.patch(
            os, "environ", {
                b"KUBERNETES_SERVICE_HOST": b"example.invalid.",
                b"KUBERNETES_SERVICE_PORT": b"443",
            },
        )

        agent = authenticate_with_serviceaccount(
            reactor, path=serviceaccount.path,
        )
        d = agent.request(b"GET", b"http://example.invalid.", headers)

        [(host, port, factory, _, _)] = reactor.tcpClients

        self.expectThat((host, port), Equals((b"example.invalid.", 80)))

        pump = ConnectionCompleter(reactor).succeedOnce()
        pump.pump()

        return server.data


    def test_bearer_token_authorization(self):
        """
        The ``IAgent`` returned adds an *Authorization* header to each request it
        issues.  The header includes the bearer token from the service account file.
        """
        token = bytes(uuid4())
        request_bytes = self._authorized_request(token=token, headers=None)

        # Sure would be nice to have an HTTP parser.
        self.assertThat(
            request_bytes,
            Contains(u"Authorization: Bearer {}".format(token).encode("ascii")),
        )


    def test_other_headers_preserved(self):
        """
        Other headers passed to the ``IAgent.request`` implementation are also
        sent in the request.
        """
        token = bytes(uuid4())
        headers = Headers({u"foo": [u"bar"]})
        request_bytes = self._authorized_request(token=token, headers=headers)
        self.expectThat(
            request_bytes,
            Contains(u"Authorization: Bearer {}".format(token).encode("ascii")),
        )
        self.expectThat(
            request_bytes,
            Contains(b"Foo: bar"),
        )
