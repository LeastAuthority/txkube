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
    certificate = field(mandatory=True, invariant=instance_of(pem.Certificate))
    key = field(mandatory=True, invariant=instance_of(pem.Key))


class NetLocation(PClass):
    host = field(mandatory=True, type=unicode)
    port = field(mandatory=True, type=(int, long))


def pick_cert(netloc, possible):
    try:
        creds = possible[netloc]
    except KeyError:
        return None

    key = ssl.KeyPair.load(creds.key.as_bytes(), FILETYPE_PEM)
    return ssl.PrivateCertificate.load(creds.certificate.as_bytes(), key, FILETYPE_PEM)


@implementer(IPolicyForHTTPS)
class ClientCertificatePolicyForHTTPS(PClass):
    credentials = pmap_field(
        NetLocation, TLSCredentials,
    )

    trust_roots = pmap_field(
        NetLocation, pem.Certificate,
    )

    def creatorForNetloc(self, hostname, port):
        hostname = hostname.decode("ascii")

        netloc = NetLocation(host=hostname, port=port)
        client_cert = pick_cert(netloc, self.credentials)

        try:
            trust_cert = self.trust_roots[netloc]
        except KeyError:
            trust_root = None
        else:
            trust_root = ssl.trustRootFromCertificates([
                ssl.Certificate.load(trust_cert.as_bytes(), FILETYPE_PEM),
            ])

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
