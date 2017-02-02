# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube._model``.
"""

from json import loads, dumps

from zope.interface.verify import verifyObject

from testtools.matchers import (
    Equals, MatchesStructure, Not, Is, Contains, ContainsAll, raises,
)

from hypothesis import given, assume
from hypothesis.strategies import choices

from ..testing import TestCase
from ..testing.matchers import PClassEquals, MappingEquals
from ..testing.strategies import (
    object_name,
    iobjects,
    namespacelists,
)

from .. import (
    UnrecognizedVersion, UnrecognizedKind,
    IObject, v1, iobject_to_raw, iobject_from_raw,
)


class IObjectTests(TestCase):
    """
    Tests for ``IObject``.
    """
    @given(obj=iobjects())
    def test_interface(self, obj):
        """
        The object provides ``IObject``.
        """
        verifyObject(IObject, obj)


    @given(obj=iobjects())
    def test_serialization_roundtrip(self, obj):
        """
        An ``IObject`` provider can be round-trip through JSON using
        ``iobject_to_raw`` and ``iobject_from_raw``.
        """
        marshalled = iobject_to_raw(obj)

        # Every IObject has these marshalled fields - and when looking at the
        # marshalled form, they're necessary to figure out the
        # schema/definition for the data.  We can't say anything in general
        # about the *values* (because of things like "extensions/v1beta1") but
        # we can at least assert the keys are present.
        self.expectThat(marshalled, ContainsAll([u"kind", u"apiVersion"]))

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


    def test_unknown_version(self):
        """
        ``iobject_from_raw`` raises ``UnrecognizedVersion`` if it does not
        recognize the *apiVersion* in the given data.
        """
        obj = {
            u"apiVersion": u"invalid.example.txkube",
            u"kind": u"Service",
        }
        self.assertThat(
            lambda: iobject_from_raw(obj),
            raises(UnrecognizedVersion(obj[u"apiVersion"], obj)),
        )


    def test_unknown_kind(self):
        """
        ``iobject_from_raw`` raises ``UnrecognizedKind`` if it does not recognize
        the *kind* in the given data.
        """

        obj = {
            u"apiVersion": u"v1",
            u"kind": u"SomethingFictional",
        }
        self.assertThat(
            lambda: iobject_from_raw(obj),
            raises(UnrecognizedKind(u"v1", u"SomethingFictional", obj)),
        )



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



class NamespaceListTests(TestCase):
    """
    Tests for ``NamespaceList``.
    """
    @given(collection=namespacelists(), choose=choices())
    def test_remove(self, collection, choose):
        """
        ``NamespaceList.remove`` creates a new ``NamespaceList`` which does not
        have the given item.
        """
        assume(len(collection.items) > 0)
        item = choose(collection.items)
        removed = collection.remove(item)
        self.assertThat(removed.items, Not(Contains(item)))


    @given(collection=namespacelists(), choose=choices())
    def test_item_by_name(self, collection, choose):
        """
        ``NamespaceList.item_by_name`` returns the ``Namespace`` with the matching
        name.
        """
        assume(len(collection.items) > 0)
        for item in collection.items:
            self.expectThat(collection.item_by_name(item.metadata.name), Is(item))

        item = choose(collection.items)
        collection = collection.remove(item)
        self.expectThat(
            lambda: collection.item_by_name(item.metadata.name),
            raises(KeyError(item.metadata.name)),
        )
