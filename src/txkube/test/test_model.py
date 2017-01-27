# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube._model``.
"""

from json import loads, dumps

from testtools.matchers import Equals, LessThan, MatchesStructure

from hypothesis import given, assume

from ..testing import TestCase
from ..testing.strategies import (
    object_name,
    retrievable_namespaces, creatable_namespaces,
    configmaps,
    objectcollections,
)

from .. import (
    Namespace, ConfigMap, ObjectCollection,
)


def iobject_tests(loader, strategy):
    class Tests(TestCase):
        """
        Tests for ``IObject`` and ``IObjectLoader``.
        """
        @given(obj=strategy())
        def test_roundtrip(self, obj):
            """
            ``IObject`` providers can be round-trip through a simplified object graph
            using ``IObject.to_raw`` and ``IObjectLoader.from_raw``.
            """
            marshalled = obj.to_raw()

            # ``IObject`` providers include *kind* and *apiVersion* in their
            # serialized forms.
            self.expectThat(marshalled[u"kind"], Equals(obj.kind))
            self.expectThat(marshalled[u"apiVersion"], Equals(obj.apiVersion))

            reloaded = loader.from_raw(marshalled)
            remarshalled = reloaded.to_raw()
            self.expectThat(obj, Equals(reloaded))
            self.expectThat(marshalled, Equals(remarshalled))

            # The serialized form can also be round-tripped through JSON.
            self.expectThat(marshalled, Equals(loads(dumps(marshalled))))


        @given(obj=strategy())
        def test_kind_and_version(self, obj):
            """
            """
            marshalled = obj.to_raw()

    return Tests



class RetrievableNamespaceTests(iobject_tests(Namespace, retrievable_namespaces)):
    """
    Tests for ``Namespace`` based on a strategy for fully-populated objects.
    """



class CreatableNamespaceTests(iobject_tests(Namespace, creatable_namespaces)):
    """
    Tests for ``Namespace`` based on a strategy for objects just detailed
    enough to be created.
    """


class NamespaceTests(TestCase):
    """
    Other tests for ``Namespace``.
    """
    def test_default(self):
        """
        ``Namespace.default`` returns the *default* namespace.
        """
        self.assertThat(
            Namespace.default(),
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
            Namespace.named(name),
            MatchesStructure(
                metadata=MatchesStructure(
                    name=Equals(name),
                ),
            ),
        )


class ConfigMapTests(iobject_tests(ConfigMap, configmaps)):
    """
    Tests for ``ConfigMap``.
    """



class ObjectCollectionTests(iobject_tests(ObjectCollection, objectcollections)):
    """
    Tests for ``ObjectCollection``.
    """
    @given(a=configmaps(), b=configmaps())
    def test_items_sorted(self, a, b):
        """
        ``ObjectCollection.items`` is sorted by (namespace, name) regardless of
        the order given to the initializer.
        """
        assume(
            (a.metadata.namespace, a.metadata.name)
            != (b.metadata.namespace, b.metadata.name)
        )

        collection = ObjectCollection.of(ConfigMap, items=[a, b])
        first = collection.items[0].metadata
        second = collection.items[1].metadata

        self.assertThat(
            (first.namespace, first.name),
            LessThan((second.namespace, second.name)),
        )

    def test_kind(self):
        """
        ``ObjectCollection.kind`` always reflects the type of its items.
        """
        self.expectThat(
            ObjectCollection.of(Namespace).kind, Equals(u"NamespaceList"),
        )
        self.expectThat(
            ObjectCollection.of(ConfigMap).kind, Equals(u"ConfigMapList"),
        )
