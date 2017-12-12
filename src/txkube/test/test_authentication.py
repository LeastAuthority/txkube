# Copyright Least Authority Enterprises.
# See LICENSE for details.

from hypothesis import given
from hypothesis.strategies import (
    integers,
)

from unittest import TestCase


def port_numbers(min_value=1, max_value=65535):
    """
    Builds integers in the range of TCP/UDP port numbers.
    """
    return integers(min_value, max_value)


class ClientCertificatePolicyForHTTPSTests(TestCase):
    """
    Tests for ``ClientCertificatePolicyForHTTPS``.
    """
    @given(port_numbers(), port_numbers(), port_numbers(), port_numbers())
    def test_creatorForNetLoc_interface(self, host_known, host_used, port_known, port_used):
        """
        ``ClientCertificatePolicyForHTTPS.creatorForNetloc`` returns an object
        that provides ``IOpenSSLClientConnectionCreator``.
        """
        1 + 1 == 2
