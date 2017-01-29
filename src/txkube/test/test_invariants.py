# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube._invariants``.
"""

from zope.interface import Interface, implementer

from pyrsistent import InvariantException, PClass, field

from ..testing import TestCase
from .._invariants import instance_of, provider_of


class IDummy(Interface):
    pass



@implementer(IDummy)
class Dummy(PClass):
    an_int = field(invariant=instance_of(int))
    an_interface = field(invariant=provider_of(IDummy))



class InstanceOfTests(TestCase):
    """
    Tests for ``instance_of``.
    """
    def test_valid(self):
        self.assertEqual(3, Dummy(an_int=3).an_int)


    def test_invalid(self):
        self.assertRaises(
            InvariantException,
            lambda: Dummy(an_int=b"bytes"),
        )




class ProviderOfTests(TestCase):
    """
    Tests for ``provider_of``.
    """
    def test_valid(self):
        d = Dummy()
        self.assertIs(d, Dummy(an_interface=d).an_interface)


    def test_invalid(self):
        self.assertRaises(
            InvariantException,
            lambda: Dummy(an_interface=b"bytes"),
        )
