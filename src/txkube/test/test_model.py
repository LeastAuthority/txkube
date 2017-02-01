# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube._model``.
"""

from json import loads, dumps

from testtools.matchers import (
    Equals, LessThan, MatchesStructure, Not, Is,
)

from hypothesis import given, assume

from ..testing import TestCase
from ..testing.matchers import PClassEquals, MappingEquals
from ..testing.strategies import (
    object_name,
    iobjects,
    creatable_namespaces,
)

from .. import v1, iobject_to_raw, iobject_from_raw


class IObjectTests(TestCase):
    """
    Tests for ``IObject``.
    """
    @given(obj=iobjects())
    def test_serialization_roundtrip(self, obj):
        """
        An ``IObject`` provider can be round-trip through JSON using
        ``iobject_to_raw`` and ``iobject_from_raw``.
        """
        # XXX Fix this!
        assume(not obj.kind.endswith(u"List"))

        marshalled = iobject_to_raw(obj)

        # Every IObject has these marshalled fields - and when looking at
        # the marshalled form, they're necessary to figure out the
        # schema/definition for the data.
        self.expectThat(marshalled[u"kind"], Equals(obj.kind))
        self.expectThat(marshalled[u"apiVersion"], Equals(obj.apiVersion))

        # We should be able to unmarshal the data back to the same model
        # object as we started with.
        reloaded = iobject_from_raw(marshalled)
        self.expectThat(obj, PClassEquals(reloaded))

        # And, to be extra sure (ruling out any weird Python object
        # semantic hijinx), that that reconstituted object should marshal
        # back to exactly the same simplified object graph.
        remarshalled = iobject_to_raw(reloaded)
        self.expectThat(marshalled, MappingEquals(remarshalled))

        # Also, the marshalled form must be JSON compatible.
        serialized = dumps(marshalled)
        deserialized = loads(serialized)
        self.expectThat(marshalled, MappingEquals(deserialized))



class NamespaceTests(TestCase):
    """
    Other tests for ``Namespace``.
    """
    def test_default(self):
        """
        ``Namespace.default`` returns the *default* namespace.
        """
        self.assertThat(
            v1.Namespace.default(),
            MatchesStructure(
                metadata=MatchesStructure(
                    name=Equals(u"default"),
                ),
            ),
        )


    @given(object_name())
    def test_named(self, name):
        """
        ``Namespace.named`` returns a ``Namespace`` model object with the given
        name.
        """
        self.assertThat(
            v1.Namespace.named(name),
            MatchesStructure(
                metadata=MatchesStructure(
                    name=Equals(name),
                ),
            ),
        )


    def test_fill_defaults(self):
        """
        ``Namespace.fill_defaults`` returns a ``Namespace`` with *uid* metadata
        and an active *status*.
        """
        # If they are not set already, a uid is generated and put into the
        # metadata and the status is set to active.
        sparse = v1.Namespace.named(u"foo")
        filled = sparse.fill_defaults()
        self.expectThat(
            filled,
            MatchesStructure(
                metadata=MatchesStructure(
                    uid=Not(Is(None)),
                ),
                status=Equals(v1.NamespaceStatus.active()),
            ),
        )



class ConfigMapTests(TestCase):
    """
    Tests for ``ConfigMap``.
    """
    @given(namespace=object_name(), name=object_name())
    def test_named(self, namespace, name):
        """
        ``ConfigMap.named`` returns a ``ConfigMap`` model object with the given
        namespace and name.
        """
        self.assertThat(
            v1.ConfigMap.named(namespace, name),
            MatchesStructure(
                metadata=MatchesStructure(
                    namespace=Equals(namespace),
                    name=Equals(name),
                ),
            ),
        )
