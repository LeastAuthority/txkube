# Copyright Least Authority Enterprises.
# See LICENSE for details.

__all__ = [
    "strategies",
    "integration",
    "TestCase", "AsynchronousDeferredRunTest",
    "assertNoResult",
    "cert",
]

from ._testcase import (
    TestCase,
    AsynchronousDeferredRunTest,
    assertNoResult,
)

from cryptography.x509 import (
    CertificateBuilder,
    SubjectAlternativeName,
    BasicConstraints,
    DNSName,
    Name,
    NameAttribute,
    random_serial_number,
)
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.backends import default_backend

from datetime import datetime, timedelta

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
    return builder.public_key(pubkey,
    ).serial_number(random_serial_number(),
    ).not_valid_before(datetime.utcnow(),
    ).not_valid_after(datetime.utcnow() + timedelta(seconds=1),
    ).sign(privkey, SHA256(), default_backend(),
    )
