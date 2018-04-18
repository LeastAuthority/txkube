# Copyright Least Authority Enterprises.
# See LICENSE for details.

import os
from itertools import count, islice
from uuid import uuid4

from pykube import KubeConfig

import pem

import attr

from pyrsistent import InvariantException

from hypothesis import given

from fixtures import TempDir

from zope.interface.verify import verifyObject

from testtools import ExpectedException
from testtools.matchers import (
    AfterPreprocessing, Equals, Contains, IsInstance, raises
)
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from zope.interface import implementer

from twisted.python.compat import unicode
from twisted.python.filepath import FilePath
from twisted.internet.address import IPv4Address
from twisted.internet.error import DNSLookupError
from twisted.internet.interfaces import (
    IHostResolution,
    IReactorPluggableNameResolver,
    IOpenSSLClientConnectionCreator,
)
from twisted.internet.protocol import Factory
from twisted.web.iweb import IPolicyForHTTPS
from twisted.web.http_headers import Headers
from twisted.test.iosim import ConnectionCompleter
from twisted.test.proto_helpers import AccumulatingProtocol, MemoryReactorClock

from ..testing import TestCase, assertNoResult, cert
from ..testing.strategies import (
    dns_subdomains,
    port_numbers,
)

from .._authentication import (
    ClientCertificatePolicyForHTTPS,
    NetLocation,
    Certificates,
    Chain,
    pairwise,
    https_policy_from_config,
)
from .. import authenticate_with_serviceaccount
from ._compat import encode_environ

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

# Let hostname u"example.invalid" map to an
# IPv4 address in the TEST-NET range.
HOST_MAP = {
    u"example.invalid.": "192.0.2.2"
}

def create_reactor():
    """
    Twisted 17.1.0 and higher requires a reactor which implements
    ``IReactorPluggableNameResolver``.
    """

    @implementer(IHostResolution)
    @attr.s
    class Resolution(object):
        name = attr.ib()

    class _FakeResolver(object):

        def resolveHostName(self, resolutionReceiver, hostName, *args,  **kwargs):
            portNumber = kwargs.pop('portNumber')
            r = Resolution(name=hostName)

            resolutionReceiver.resolutionBegan(r)
            if hostName in HOST_MAP:
                resolutionReceiver.addressResolved(
                    IPv4Address('TCP', HOST_MAP[hostName], portNumber))
            resolutionReceiver.resolutionComplete()
            return r

    @implementer(IReactorPluggableNameResolver)
    class _ResolvingMemoryClockReactor(MemoryReactorClock):
        nameResolver = _FakeResolver()

    return _ResolvingMemoryClockReactor()



class AuthenticateWithServiceAccountTests(TestCase):
    """
    Tests for ``authenticate_with_serviceaccount``.
    """
    def _authorized_request(self, token, headers,
                            kubernetes_host=b"example.invalid."):
        """
        Get an agent using ``authenticate_with_serviceaccount`` and issue a
        request with it.

        :return bytes: The bytes of the request the agent issues.
        """
        server = AccumulatingProtocol()
        factory = Factory.forProtocol(lambda: server)
        factory.protocolConnectionMade = None

        reactor = create_reactor()
        reactor.listenTCP(80, factory)

        t = FilePath(self.useFixture(TempDir()).path)
        t = t.asBytesMode()
        serviceaccount = t.child(b"serviceaccount")
        serviceaccount.makedirs()

        serviceaccount.child(b"ca.crt").setContent(_CA_CERT_PEM)
        serviceaccount.child(b"token").setContent(token)

        environ = encode_environ(
            {
                u"KUBERNETES_SERVICE_HOST": kubernetes_host.decode("ascii"),
                u"KUBERNETES_SERVICE_PORT": u"443"
            })
        self.patch(os, "environ", environ)

        agent = authenticate_with_serviceaccount(
            reactor, path=serviceaccount.asTextMode().path,
        )

        d = agent.request(b"GET", b"http://" + kubernetes_host, headers)
        assertNoResult(self, d)
        [(host, port, factory, _, _)] = reactor.tcpClients

        addr = HOST_MAP.get(kubernetes_host.decode("ascii"), None)
        self.expectThat((host, port), Equals((addr, 80)))

        pump = ConnectionCompleter(reactor).succeedOnce()
        pump.pump()

        return server.data


    def test_bearer_token_authorization(self):
        """
        The ``IAgent`` returned adds an *Authorization* header to each request it
        issues.  The header includes the bearer token from the service account
        file.
        """
        token = str(uuid4())
        if isinstance(token, unicode):
            token = token.encode("ascii")
        request_bytes = self._authorized_request(token=token, headers=None)

        # Sure would be nice to have an HTTP parser.
        self.assertThat(
            request_bytes,
            Contains(b"Authorization: Bearer " + token),
        )


    def test_hostname_does_not_resolve(self):
        """
        Specifying a hostname which cannot be resolved to an
        IP address will result in an ``DNSLookupError``.
        """
        with ExpectedException(DNSLookupError, "DNS lookup failed: no results "
                               "for hostname lookup: doesnotresolve."):
            self._authorized_request(
                token=b"test",
                headers=Headers({}),
                kubernetes_host=b"doesnotresolve"
            )


    def test_other_headers_preserved(self):
        """
        Other headers passed to the ``IAgent.request`` implementation are also
        sent in the request.
        """
        token = str(uuid4())
        if isinstance(token, unicode):
            token = token.encode("ascii")
        headers = Headers({u"foo": [u"bar"]})
        request_bytes = self._authorized_request(token=token, headers=headers)
        self.expectThat(
            request_bytes,
            Contains(b"Authorization: Bearer " + token),
        )
        self.expectThat(
            request_bytes,
            Contains(b"Foo: bar"),
        )



class HTTPSPolicyFromConfigTests(TestCase):
    """
    Tests for ``https_policy_from_config``.
    """
    def test_policy(self):
        """
        ``https_policy_from_config`` returns a ``ClientCertificatePolicyForHTTPS``
        with no credentials but with trust roots taken from the Kubernetes
        *serviceaccount* directory it is pointed at.  It also respects
        *KUBERNETES_...* environment variables to identify the address of the
        server.
        """
        t = FilePath(self.useFixture(TempDir()).path)
        t = t.asBytesMode()
        serviceaccount = t.child(b"serviceaccount")
        serviceaccount.makedirs()

        serviceaccount.child(b"ca.crt").setContent(_CA_CERT_PEM)
        serviceaccount.child(b"token").setContent(b"token")

        netloc = NetLocation(host=u"example.invalid", port=443)
        environ = encode_environ({
                u"KUBERNETES_SERVICE_HOST": netloc.host,
                u"KUBERNETES_SERVICE_PORT": u"{}".format(netloc.port),
        })
        self.patch(os, "environ", environ)

        config = KubeConfig.from_service_account(path=serviceaccount.asTextMode().path)

        policy = https_policy_from_config(config)
        self.expectThat(
            policy,
            Equals(
                ClientCertificatePolicyForHTTPS(
                    credentials={},
                    trust_roots={
                        netloc: pem.parse(_CA_CERT_PEM)[0],
                    },
                ),
            ),
        )


    def test_missing_ca_certificate(self):
        """
        If no CA certificate is found in the service account directory,
        ``https_policy_from_config`` raises ``ValueError``.
        """
        t = FilePath(self.useFixture(TempDir()).path)
        t = t.asBytesMode()
        serviceaccount = t.child(b"serviceaccount")
        serviceaccount.makedirs()

        serviceaccount.child(b"ca.crt").setContent(b"not a cert pem")
        serviceaccount.child(b"token").setContent(b"token")

        environ = encode_environ({
            u"KUBERNETES_SERVICE_HOST": u"example.invalid.",
            u"KUBERNETES_SERVICE_PORT": u"443",
        })
        self.patch(os, "environ", environ)

        config = KubeConfig.from_service_account(path=serviceaccount.asTextMode().path)
        self.assertThat(
            lambda: https_policy_from_config(config),
            raises(ValueError("No certificate authority certificate found.")),
        )


    def test_bad_ca_certificate(self):
        """
        If no CA certificate is found in the service account directory,
        ``https_policy_from_config`` raises ``ValueError``.
        """
        t = FilePath(self.useFixture(TempDir()).path)
        t = t.asBytesMode()
        serviceaccount = t.child(b"serviceaccount")
        serviceaccount.makedirs()

        serviceaccount.child(b"ca.crt").setContent(
            b"-----BEGIN CERTIFICATE-----\n"
            b"not a cert pem\n"
            b"-----END CERTIFICATE-----\n"
        )
        serviceaccount.child(b"token").setContent(b"token")

        environ = encode_environ({
            u"KUBERNETES_SERVICE_HOST": u"example.invalid.",
            u"KUBERNETES_SERVICE_PORT": u"443",
        })
        self.patch(os, "environ", environ)

        config = KubeConfig.from_service_account(path=serviceaccount.asTextMode().path)
        self.assertThat(
            lambda: https_policy_from_config(config),
            raises(ValueError(
                "Invalid certificate authority certificate found.",
                "[('PEM routines', 'PEM_read_bio', 'bad base64 decode')]",
            )),
        )



class ClientCertificatePolicyForHTTPSTests(TestCase):
    """
    Tests for ``ClientCertificatePolicyForHTTPS``.
    """
    def test_interface(self):
        """
        ``ClientCertificatePolicyForHTTPS`` instances provide ``IPolicyForHTTPS``.
        """
        policy = ClientCertificatePolicyForHTTPS(
            credentials={},
            trust_roots={},
        )
        verifyObject(IPolicyForHTTPS, policy)


    @given(dns_subdomains(), dns_subdomains(), port_numbers(), port_numbers())
    def test_creatorForNetLoc_interface(self, host_known, host_used, port_known, port_used):
        """
        ``ClientCertificatePolicyForHTTPS.creatorForNetloc`` returns an object
        that provides ``IOpenSSLClientConnectionCreator``.
        """
        netloc = NetLocation(host=host_known, port=port_known)
        cert = pem.parse(_CA_CERT_PEM)[0]

        policy = ClientCertificatePolicyForHTTPS(
            credentials={},
            trust_roots={
                netloc: cert,
            },
        )
        creator = policy.creatorForNetloc(
            host_used.encode("ascii"),
            port_used,
        )
        verifyObject(IOpenSSLClientConnectionCreator, creator)



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

        a_cert = cert(u"a.invalid", u"a.invalid", a_key.public_key(), a_key, True)
        b_cert = cert(u"a.invalid", u"b.invalid", b_key.public_key(), a_key, True)
        c_cert = cert(u"b.invalid", u"c.invalid", c_key.public_key(), b_key, False)

        a, b, c = pem.parse(b"\n".join(
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
