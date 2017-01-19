# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube._model``.
"""

from testtools.matchers import Equals, raises

from pyrsistent import InvariantException

from hypothesis import given
from hypothesis.strategies import choices

from ..testing import TestCase
from ..testing.strategies import (
    object_metadatas, namespaced_object_metadatas, namespaces, configmaps,
    objectcollections,
)

from .._model import (
    ObjectMetadata, NamespacedObjectMetadata, Namespace, ConfigMap, ObjectCollection,
)

def object_metadata_tests(metadatas, accessors):
    """
    Generate a test case for testing a metadata type.

    :param metadatas: A strategy for generating instances of the metadata type
        to be tested.

    :param accessors: A list of metadata keys which have corresponding
        accessors.

    :return: A new ``ITestCase``.
    """
    class Tests(TestCase):
        """
        Tests common to the two different metadata types.
        """
        @given(metadata=metadatas())
        def test_accessors(self, metadata):
            """
            The metadata object has several read-only properties which access common
            fields of the metadata mapping.
            """
            for name in accessors:
                self.expectThat(metadata.items[name], Equals(getattr(metadata, name)))


        @given(metadata=metadatas(), choice=choices())
        def test_required(self, metadata, choice):
            """
            The metadata object requires values corresponding to each of its
            accessors.
            """
            arbitrary_key = choice(accessors)
            missing_one = metadata.items.discard(arbitrary_key)
            self.expectThat(
                lambda: metadata.set(items=missing_one),
                raises(InvariantException),
            )

    return Tests



class ObjectMetadataTests(
    object_metadata_tests(object_metadatas, [u"name", u"uid"])
):
    """
    Tests for ``ObjectMetadata``.
    """



class NamespacedObjectMetadataTests(
    object_metadata_tests(namespaced_object_metadatas, [u"name", u"uid", u"namespace"])
):
    """
    Tests for ``NamespacedObjectMetadata``.
    """


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



class NamespaceTests(iobject_tests(Namespace, namespaces)):
    """
    Tests for ``Namespace``.
    """



class ConfigMapTests(iobject_tests(ConfigMap, configmaps)):
    """
    Tests for ``ConfigMap``.
    """



class ObjectCollectionTests(iobject_tests(ObjectCollection, objectcollections)):
    """
    Tests for ``ObjectCollection``.
    """
