# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube._model``.
"""

from testtools.matchers import (
    Equals, LessThan, MatchesStructure, Not, Is,
)

from hypothesis import given, assume

from ..testing import TestCase
from ..testing.strategies import (
    object_name,
    retrievable_namespaces, creatable_namespaces,
    configmaps,
    objectcollections,
)

from .. import (
    v1, ConfigMap, ObjectCollection,
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
            reloaded = loader.from_raw(marshalled)
            remarshalled = reloaded.to_raw()
            self.expectThat(obj, Equals(reloaded))
            self.expectThat(marshalled, Equals(remarshalled))

    return Tests



class RetrievableNamespaceTests(iobject_tests(v1.Namespace, retrievable_namespaces)):
    """
    Tests for ``Namespace`` based on a strategy for fully-populated objects.
    """



class CreatableNamespaceTests(iobject_tests(v1.Namespace, creatable_namespaces)):
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



class ConfigMapTests(iobject_tests(ConfigMap, configmaps)):
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
            ConfigMap.named(namespace, name),
            MatchesStructure(
                metadata=MatchesStructure(
                    namespace=Equals(namespace),
                    name=Equals(name),
                ),
            ),
        )




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

        collection = ObjectCollection(items=[a, b])
        first = collection.items[0].metadata
        second = collection.items[1].metadata

        self.assertThat(
            (first.namespace, first.name),
            LessThan((second.namespace, second.name)),
        )
