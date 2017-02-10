# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube.memory_kubernetes``.
"""

from zope.interface.verify import verifyClass

from hypothesis import given

from testtools.matchers import Equals, Is, IsInstance, AfterPreprocessing

from ..testing.integration import kubernetes_client_tests
from ..testing.strategies import iobjects
from ..testing import TestCase

from .. import memory_kubernetes
from .._memory import (
    _KubernetesState, IAgency, NullAgency, _incrementResourceVersion,
)


def get_kubernetes(case):
    """
    Create an in-memory test double provider of ``IKubernetes``.
    """
    return memory_kubernetes()



class KubernetesClientIntegrationTests(kubernetes_client_tests(get_kubernetes)):
    """
    Integration tests which interact with an in-memory-only Kubernetes
    deployment via ``txkube.memory_kubernetes``.
    """



class NullAgencyTests(TestCase):
    """
    Tests for ``NullAgency``.
    """
    def test_interface(self):
        """
        ``NullAgency`` implements ``IAgency``.
        """
        verifyClass(IAgency, NullAgency)


    @given(iobjects())
    def test_before_create(self, obj):
        """
        ``NullAgency.before_create`` returns the ``IObject`` passed to it with no
        modifications.
        """
        state = _KubernetesState()
        actual = NullAgency().before_create(state, obj)
        self.assertThat(actual, Equals(obj))


    @given(iobjects())
    def test_after_create(self, obj):
        """
        ``NullAgency.after_create`` returns the ``IObject`` passed to it with no
        modifications.
        """
        state = _KubernetesState()
        actual = NullAgency().after_create(state, obj)
        self.assertThat(actual, Equals(obj))


    @given(iobjects(), iobjects())
    def test_before_replace(self, old, new):
        """
        ``NullAgency.before_replace`` returns ``None``.
        """
        state = _KubernetesState()
        actual = NullAgency().before_replace(state, old, new)
        self.assertThat(actual, Is(None))



class IncrementResourceVersionTests(TestCase):
    """
    Tests for ``_incrementResourceVersion``.
    """
    def test_missing(self):
        """
        The next version after ``None`` is ``u"1"``.
        """
        version = _incrementResourceVersion(None)
        self.expectThat(version, IsInstance(unicode))
        self.expectThat(version, Equals(u"1"))


    def test_incremented(self):
        """
        Any version other than ``None`` is interpreted as a string representation
        of an integer and incremented.
        """
        version = _incrementResourceVersion(_incrementResourceVersion(None))
        updated = _incrementResourceVersion(version)
        self.expectThat(updated, IsInstance(unicode))
        self.expectThat(updated, AfterPreprocessing(int, Equals(int(version) + 1)))
