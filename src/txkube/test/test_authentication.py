# Copyright Least Authority Enterprises.
# See LICENSE for details.

import os
from itertools import count, islice
from uuid import uuid4
from datetime import datetime, timedelta

import pem

from pyrsistent import InvariantException

from fixtures import TempDir

from testtools.matchers import AfterPreprocessing, Equals, Contains, IsInstance, raises

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives import serialization
from cryptography.x509 import (
    CertificateBuilder,
    SubjectAlternativeName,
    BasicConstraints,
    DNSName,
    Name,
    NameAttribute,
)
from cryptography.hazmat.backends import default_backend

from twisted.python.filepath import FilePath
from twisted.internet.protocol import Factory
from twisted.web.http_headers import Headers
from twisted.test.iosim import ConnectionCompleter
from twisted.test.proto_helpers import AccumulatingProtocol, MemoryReactor

from ..testing import TestCase

from .._authentication import Certificates, Chain, pairwise
from .. import authenticate_with_serviceaccount

# Just an arbitrary certificate pulled off the internet.  Details ought not
# matter.  Retrieved using:
#
#    $ openssl s_client -showcerts -connect google.com:443
#
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
        agent.request(b"GET", b"http://example.invalid.", headers)

        [(host, port, factory, _, _)] = reactor.tcpClients

        self.expectThat((host, port), Equals((b"example.invalid.", 80)))

        pump = ConnectionCompleter(reactor).succeedOnce()
        pump.pump()

        return server.data


    def test_http_bearer_token_authorization(self):
        """
        The ``IAgent`` returned adds an *Authorization* header to each request it
        issues.  The header includes the bearer token from the service account
        file.  This works over HTTP.
        """
        token = bytes(uuid4())
        request_bytes = self._authorized_request(token=token, headers=None)

        # Sure would be nice to have an HTTP parser.
        self.assertThat(
            request_bytes,
            Contains(u"Authorization: Bearer {}".format(token).encode("ascii")),
        )


    def test_https_bearer_token_authorization(self):
        """
        The ``IAgent`` returned adds an *Authorization* header to each request it
        issues.  The header includes the bearer token from the service account
        file.  This works over HTTPS.
        """
        # This test duplicates a lot of logic from _authorized_request because
        # ConnectionCompleter doesn't work with TLS connections by itself.
        server = AccumulatingProtocol()
        factory = Factory.forProtocol(lambda: server)
        factory.protocolConnectionMade = None

        reactor = MemoryReactor()
        reactor.listenTCP(443, factory)

        token = bytes(uuid4())

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
        headers = Headers()
        agent.request(b"GET", b"https://example.invalid.", headers)

        [connection] = reactor.sslClients
        (host, port, factory) = connection[:3]
        # Put it somewhere ConnectionCompleter can deal with.
        reactor.tcpClients.append((host, port, factory, None, None))

        pump = ConnectionCompleter(reactor).succeedOnce()
        pump.pump()

        request_bytes = server.data
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


    def test_missing_ca_certificate(self):
        """
        If no CA certificate is found in the service account directory,
        ``authenticate_with_serviceaccount`` raises ``ValueError``.
        """
        t = FilePath(self.useFixture(TempDir()).join(b""))
        serviceaccount = t.child(b"serviceaccount")
        serviceaccount.makedirs()

        serviceaccount.child(b"ca.crt").setContent(b"not a cert pem")
        serviceaccount.child(b"token").setContent(b"token")

        self.patch(
            os, "environ", {
                b"KUBERNETES_SERVICE_HOST": b"example.invalid.",
                b"KUBERNETES_SERVICE_PORT": b"443",
            },
        )

        self.assertThat(
            lambda: authenticate_with_serviceaccount(
                MemoryReactor(), path=serviceaccount.path,
            ),
            raises(ValueError("No certificate authority certificate found.")),
        )


    def test_bad_ca_certificate(self):
        """
        If no CA certificate is found in the service account directory,
        ``authenticate_with_serviceaccount`` raises ``ValueError``.
        """
        t = FilePath(self.useFixture(TempDir()).join(b""))
        serviceaccount = t.child(b"serviceaccount")
        serviceaccount.makedirs()

        serviceaccount.child(b"ca.crt").setContent(
            b"-----BEGIN CERTIFICATE-----\n"
            b"not a cert pem\n"
            b"-----END CERTIFICATE-----\n"
        )
        serviceaccount.child(b"token").setContent(b"token")

        self.patch(
            os, "environ", {
                b"KUBERNETES_SERVICE_HOST": b"example.invalid.",
                b"KUBERNETES_SERVICE_PORT": b"443",
            },
        )

        self.assertThat(
            lambda: authenticate_with_serviceaccount(
                MemoryReactor(), path=serviceaccount.path,
            ),
            raises(ValueError(
                "Invalid certificate authority certificate found.",
                "[('PEM routines', 'PEM_read_bio', 'bad base64 decode')]",
            )),
        )



class PairwiseTests(TestCase):
    """
    Tests for ``pairwise``.
    """
    def test_pairs(self):
        a = object()
        b = object()
        c = object()
        d = object()

        self.expectThat(
            pairwise([]),
            AfterPreprocessing(list, Equals([])),
        )
        self.expectThat(
            pairwise([a]),
            AfterPreprocessing(list, Equals([])),
        )
        self.expectThat(
            pairwise([a, b]),
            AfterPreprocessing(list, Equals([(a, b)])),
        )

        self.expectThat(
            pairwise([a, b, c]),
            AfterPreprocessing(list, Equals([(a, b), (b, c)])),
        )
        self.expectThat(
            pairwise([a, b, c, d]),
            AfterPreprocessing(list, Equals([(a, b), (b, c), (c, d)])),
        )


    def test_lazy(self):
        """
        ``pairwise`` only consumes as much of its iterable argument as necessary
        to satisfy iteration of its own result.
        """
        self.expectThat(
            islice(pairwise(count()), 3),
            AfterPreprocessing(list, Equals([(0, 1), (1, 2), (2, 3)])),
        )



class ChainTests(TestCase):
    """
    Tests for ``Chain``.
    """
    def test_empty(self):
        """
        A ``Chain`` must have certificates.
        """
        self.assertRaises(
            InvariantException,
            lambda: Chain(certificates=Certificates([])),
        )


    def test_ordering(self):
        """
        Each certificate in ``Chain`` must be signed by the following certificate.
        """
        a_key, b_key, c_key = tuple(
            rsa.generate_private_key(
                public_exponent=65537,
                key_size=512,
                backend=default_backend(),
            )
            for i in range(3)
        )

        def cert(issuer, subject, pubkey, privkey, ca):
            builder = CertificateBuilder(
            ).issuer_name(
                Name([NameAttribute(NameOID.COMMON_NAME, issuer)]),
            ).subject_name(
                Name([NameAttribute(NameOID.COMMON_NAME, subject)]),
            ).add_extension(
                SubjectAlternativeName([DNSName(subject)]),
                critical=False,
            )
            if ca:
                builder = builder.add_extension(
                    BasicConstraints(True, None),
                    critical=True,
                )
            return builder.public_key(a_key.public_key(),
            ).serial_number(1,
            ).not_valid_before(datetime.utcnow(),
            ).not_valid_after(datetime.utcnow() + timedelta(seconds=1),
            ).sign(a_key, SHA256(), default_backend(),
            )

        a_cert = cert(u"a.invalid", u"a.invalid", a_key.public_key(), a_key, True)
        b_cert = cert(u"a.invalid", u"b.invalid", b_key.public_key(), a_key, True)
        c_cert = cert(u"b.invalid", u"c.invalid", c_key.public_key(), b_key, False)

        a, b, c = pem.parse("\n".join(
            cert.public_bytes(serialization.Encoding.PEM)
            for cert
            in (a_cert, b_cert, c_cert)
        ))

        # a is not signed by b.  Rather, the reverse.  Therefore this ordering
        # is an error.
        self.expectThat(
            lambda: Chain(certificates=Certificates([c, a, b])),
            raises(InvariantException),
        )
        # c is signed by b and b is signed by a.  Therefore this is perfect.
        self.expectThat(
            Chain(certificates=Certificates([c, b, a])),
            IsInstance(Chain),
        )
