# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Kubernetes authentication support.
"""

import pem

from OpenSSL.crypto import FILETYPE_PEM

from zope.interface import implementer

from pyrsistent import PClass, field, pmap_field

from twisted.internet import ssl
from twisted.web.iweb import IPolicyForHTTPS
from twisted.web.client import Agent

from ._invariants import instance_of

class TLSCredentials(PClass):
    """
    ``TLSCredentials`` holds the information necessary to use a client
    certificate for a TLS handshake.

    :ivar pem.Certificate certificate: The client certificate to use.
    :ivar pem.Key key: The private key which corresponds to ``certificate``.
    """
    certificate = field(mandatory=True, invariant=instance_of(pem.Certificate))
    key = field(mandatory=True, invariant=instance_of(pem.Key))


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

    :return: A ``twisted.internet.ssl.PrivateCertificate`` instance
        representing them if credentials are found.  Otherwise, ``None``.
    """
    try:
        creds = possible[netloc]
    except KeyError:
        return None

    key = ssl.KeyPair.load(creds.key.as_bytes(), FILETYPE_PEM)
    return ssl.PrivateCertificate.load(creds.certificate.as_bytes(), key, FILETYPE_PEM)


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
        trust_cert = self.trust_roots[netloc]
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
        client_cert = pick_cert_for_twisted(netloc, self.credentials)
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
        )


def authenticating_agent(reactor, base_url, client_cert, client_key, ca_cert):
    """
    Create an ``IAgent`` which can issue authenticated requests to a
    particular Kubernetes server .

    :param reactor: The reactor with which to configure the resulting agent.

    :param twisted.python.url.URL base_url: The base location of the
        Kubernetes API.

    :param pem.Certificate client_cert: The client certificate to use.

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
            "authenticating_agent() makes sense for HTTPS, not {!r}".format(
                base_url.scheme
            ),
        )

    netloc = NetLocation(host=base_url.host, port=base_url.port)
    policy = ClientCertificatePolicyForHTTPS(
        credentials={
            netloc: TLSCredentials(certificate=client_cert, key=client_key),
        },
        trust_roots={
            netloc: ca_cert,
        },
    )
    return Agent(reactor, contextFactory=policy)
