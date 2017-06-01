# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Kubernetes authentication support.
"""

import pem

from OpenSSL.crypto import FILETYPE_PEM, Error as OpenSSLError

from zope.interface import implementer

from pyrsistent import CheckedPVector, PClass, field, pmap_field

from twisted.python.url import URL
from twisted.internet import ssl
from twisted.web.iweb import IPolicyForHTTPS, IAgent
from twisted.web.http_headers import Headers
from twisted.web.client import Agent

from pykube import KubeConfig

from ._invariants import instance_of


class Certificates(CheckedPVector):
    """
    A vector of ``pem.Certificate`` instances.
    """
    __type__ = pem.Certificate



class Chain(PClass):
    """
    A certificate chain.
    """
    certificates = field(mandatory=True, invariant=instance_of(Certificates))

    def __invariant__(self):
        if not self.certificates:
            return (
                False,
                "Certificate chain must contain at least one certificate.",
            )
        for subject, issuer in pairwise(self.certificates):
            subject_cert = ssl.Certificate.loadPEM(subject.as_bytes())
            subject_dn = subject_cert.getIssuer()
            issuer_dn = ssl.Certificate.loadPEM(issuer.as_bytes()).getSubject()
            if subject_dn != issuer_dn:
                return (
                    False,
                    "{} issued by {} but followed by {} in the chain".format(
                        subject_cert.getSubject(),
                        subject_dn,
                        issuer_dn,
                    ),
                )
        return (True, "")



def pairwise(iterable):
    """
    Generate consecutive pairs of elements from the given iterable.
    """
    iterator = iter(iterable)
    try:
        first = next(iterator)
    except StopIteration:
        return
    for element in iterator:
        yield first, element
        first = element



class TLSCredentials(PClass):
    """
    ``TLSCredentials`` holds the information necessary to use a client
    certificate for a TLS handshake.

    :ivar Chain chain: The client certificate chain to use.
    :ivar pem.Key key: The private key which corresponds to ``certificate``.
    """
    chain = field(mandatory=True, invariant=instance_of(Chain))
    key = field(mandatory=True, invariant=instance_of(pem.Key))

    def __invariant__(self):
        certs = list(
            ssl.Certificate.loadPEM(cert.as_bytes())
            for cert
            in self.chain.certificates
        )
        key = ssl.KeyPair.load(self.key.as_bytes(), FILETYPE_PEM)

        # Invoke CertificateOptions' key/certificate match checking logic.
        ssl.CertificateOptions(
            privateKey=key.original,
            certificate=certs[0].original,
            extraCertChain=list(cert.original for cert in certs[1:]),
        ).getContext()
        return (True, "")


class NetLocation(PClass):
    """
    ``NetLocation`` holds information which identifies a particular HTTPS
    server.  This is useful as a key for selecting the right certificate
    authority and client certificate to use.

    :ivar unicode host: The server's hostname.
    :ivar port: The server's port number.
    """
    host = field(mandatory=True, type=unicode)
    port = field(mandatory=True, type=(int, long))


def pick_cert_for_twisted(netloc, possible):
    """
    Pick the right client key/certificate to use for the given server and
    return it in the form Twisted wants.

    :param NetLocation netloc: The location of the server to consider.
    :param dict[TLSCredentials] possible: The available credentials from which
        to choose.

    :return: A two-tuple.  If no credentials were found, the elements are
        ``None`` and ``[]``.  Otherwise, the first element is a
        ``twisted.internet.ssl.PrivateCertificate`` instance representing the
        client certificate to use and the second element is a ``tuple`` of
        ``twisted.internet.ssl.Certificate`` instances representing the rest
        of the chain necessary to validate the client certificate.
    """
    try:
        creds = possible[netloc]
    except KeyError:
        return (None, ())

    key = ssl.KeyPair.load(creds.key.as_bytes(), FILETYPE_PEM)
    return (
        ssl.PrivateCertificate.load(
            creds.chain.certificates[0].as_bytes(), key, FILETYPE_PEM,
        ),
        tuple(
            ssl.Certificate.load(cert.as_bytes(), FILETYPE_PEM)
            for cert
            in creds.chain.certificates[1:]
        ),
    )


def pick_trust_for_twisted(netloc, possible):
    """
    Pick the right "trust roots" (certificate authority certificates) for the
    given server and return it in the form Twisted wants.

    Kubernetes certificates are often self-signed or otherwise exist outside
    of the typical certificate authority cartel system common for normal
    websites.  This function tries to find the right authority to use.

    :param NetLocation netloc: The location of the server to consider.
    :param dict[pem.Certificate] possible: The available certificate authority
        certificates from which to choose.

    :return: A provider of ``twisted.internet.interfaces.IOpenSSLTrustRoot``
    if there is a known certificate authority certificate for the given
    server.  Otherwise, ``None``.
    """
    try:
        trust_cert = possible[netloc]
    except KeyError:
        return None

    cert = ssl.Certificate.load(trust_cert.as_bytes(), FILETYPE_PEM)
    return ssl.trustRootFromCertificates([cert])


@implementer(IPolicyForHTTPS)
class ClientCertificatePolicyForHTTPS(PClass):
    """
    ``ClientCertificatePolicyForHTTPS`` selects the correct client certificate
    and trust roots to use for interacting with the Kubernetes API server.

    :ivar credentials: All available client certificates.
    :ivar trust_roots: All available certificate authority certificates.
    """
    credentials = pmap_field(
        NetLocation, TLSCredentials,
    )

    trust_roots = pmap_field(
        NetLocation, pem.Certificate,
    )

    def creatorForNetloc(self, hostname, port):
        """
        Pick from amongst client certs and ca certs to create a proper TLS context
        factory.

        :see: ``twisted.web.iweb.IPolicyForHTTPS``
        """
        hostname = hostname.decode("ascii")

        netloc = NetLocation(host=hostname, port=port)
        client_cert, extra_cert_chain = pick_cert_for_twisted(
            netloc, self.credentials,
        )
        trust_root = pick_trust_for_twisted(netloc, self.trust_roots)

        return ssl.optionsForClientTLS(
            # It is not necessarily the case that the certificate presented
            # will use this name but it is common to encounter self-signed
            # certificates which do use this name.  There doesn't seem to be
            # anything in the configuration file which would tell us what the
            # proper name is.  We'll probably need to make this configurable
            # at some point, I guess.
            u"kubernetes",
            clientCertificate=client_cert,
            trustRoot=trust_root,
            extraCertificateOptions=dict(
                # optionsForClientTLS gets mad if extraCertChain is () and
                # client_cert is None even though `()` clearly represents no
                # extra certificate chain.  It wants them to both be None.
                # Make it so.
                extraCertChain=tuple(cert.original for cert in extra_cert_chain) or None,
            ),
        )



def authenticate_with_certificate_chain(reactor, base_url, client_chain, client_key, ca_cert):
    """
    Create an ``IAgent`` which can issue authenticated requests to a
    particular Kubernetes server using a client certificate.

    :param reactor: The reactor with which to configure the resulting agent.

    :param twisted.python.url.URL base_url: The base location of the
        Kubernetes API.

    :param list[pem.Certificate] client_chain: The client certificate (and
        chain, if applicable) to use.

    :param pem.Key client_key: The private key to use with the client
        certificate.

    :param pem.Certificate ca_cert: The certificate authority to respect when
        verifying the Kubernetes server certificate.

    :return IAgent: An agent which will authenticate itself to a particular
        Kubernetes server and which will verify that server or refuse to
        interact with it.
    """
    if base_url.scheme != u"https":
        raise ValueError(
            "authenticate_with_certificate() makes sense for HTTPS, not {!r}".format(
                base_url.scheme
            ),
        )

    netloc = NetLocation(host=base_url.host, port=base_url.port)
    policy = ClientCertificatePolicyForHTTPS(
        credentials={
            netloc: TLSCredentials(
                chain=Chain(certificates=Certificates(client_chain)),
                key=client_key,
            ),
        },
        trust_roots={
            netloc: ca_cert,
        },
    )
    return Agent(reactor, contextFactory=policy)



def authenticate_with_certificate(reactor, base_url, client_cert, client_key, ca_cert):
    """
    See ``authenticate_with_certificate_chain``.

    :param pem.Certificate client_cert: The client certificate to use.
    """
    return authenticate_with_certificate_chain(
        reactor, base_url, [client_cert], client_key, ca_cert,
    )



@implementer(IAgent)
class HeaderInjectingAgent(PClass):
    """
    An ``IAgent`` which adds some headers to every request it makes.

    :ivar Headers _to_inject: The headers to add.
    @ivar IAgent _agent: The agent to use to issue requests.
    """
    _to_inject = field(mandatory=True)
    _agent = field(mandatory=True)

    def request(self, method, url, headers=None, bodyProducer=None):
        """
        Issue a request with some extra headers.

        :see: ``twisted.web.iweb.IAgent.request``
        """
        if headers is None:
            headers = Headers()
        else:
            headers = headers.copy()
        for k, vs in self._to_inject.getAllRawHeaders():
            headers.setRawHeaders(k, vs)
        return self._agent.request(method, url, headers, bodyProducer)



def authenticate_with_serviceaccount(reactor, **kw):
    """
    Create an ``IAgent`` which can issue authenticated requests to a
    particular Kubernetes server using a service account token.

    :param reactor: The reactor with which to configure the resulting agent.

    :param bytes path: The location of the service account directory.  The
        default should work fine for normal use within a container.

    :return IAgent: An agent which will authenticate itself to a particular
        Kubernetes server and which will verify that server or refuse to
        interact with it.
    """
    config = KubeConfig.from_service_account(**kw)

    token = config.user["token"]
    base_url = URL.fromText(config.cluster["server"].decode("ascii"))

    ca_certs = pem.parse(config.cluster["certificate-authority"].bytes())
    if not ca_certs:
        raise ValueError("No certificate authority certificate found.")
    ca_cert = ca_certs[0]

    try:
        # Validate the certificate so we have early failures for garbage data.
        ssl.Certificate.load(ca_cert.as_bytes(), FILETYPE_PEM)
    except OpenSSLError as e:
        raise ValueError(
            "Invalid certificate authority certificate found.",
            str(e),
        )

    netloc = NetLocation(host=base_url.host, port=base_url.port)
    policy = ClientCertificatePolicyForHTTPS(
        credentials={},
        trust_roots={
            netloc: ca_cert,
        },
    )

    agent = HeaderInjectingAgent(
        _to_inject=Headers({u"authorization": [u"Bearer {}".format(token)]}),
        _agent=Agent(reactor, contextFactory=policy),
    )
    return agent
