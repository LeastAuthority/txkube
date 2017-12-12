# Copyright Least Authority Enterprises.
# See LICENSE for details.

from hypothesis import given
from hypothesis.strategies import (
    integers,
)

from unittest import TestCase


class ClientCertificatePolicyForHTTPSTests(TestCase):
    """
    Tests for ``ClientCertificatePolicyForHTTPS``.
    """
    @given(integers())
    def test_foo(self, foo):
        """
        foo
        """
        1 + 1 == 2
