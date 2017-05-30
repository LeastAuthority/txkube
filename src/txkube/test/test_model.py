# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube._model``.
"""

from json import loads, dumps

from zope.interface.verify import verifyObject

from pyrsistent import (
    InvariantException,
    freeze,
)

from testtools.matchers import (
    Equals, MatchesStructure, Not, Is, Contains, ContainsAll, raises,
    IsInstance,
)

from hypothesis import given, assume
from hypothesis.strategies import choices

from ..testing import TestCase
from ..testing.matchers import (
    PClassEquals,
    MappingEquals,
    raises_exception,
)
from ..testing.strategies import (
    iobjects,
    namespacelists,
    objectcollections,
)

from .. import (
    UnrecognizedVersion, UnrecognizedKind,
    IObject, v1, v1beta1, iobject_to_raw, iobject_from_raw,
)

from .._model import set_if_none


class SerializationTests(TestCase):
    """
    Tests for ``iobject_to_raw`` and ``iobject_from_raw``.
    """
    def test_v1_apiVersion(self):
        """
        Objects from ``v1`` serialize with an *apiVersion* of ``u"v1"``.
        """
        obj = v1.ComponentStatus()
        raw = iobject_to_raw(obj)
        self.expectThat(
            raw[u"apiVersion"],
            Equals(u"v1"),
        )
        self.expectThat(
            iobject_from_raw(raw),
            IsInstance(v1.ComponentStatus),
        )


    def test_v1beta1_apiVersion(self):
        """
        Objects from ``v1beta1`` serialize with an *apiVersion* of
        ``u"extensions/v1beta1"``.
        """
        obj = v1beta1.CertificateSigningRequest()
        raw = iobject_to_raw(obj)
        self.expectThat(
            raw[u"apiVersion"],
            Equals(u"extensions/v1beta1"),
        )
        self.expectThat(
            iobject_from_raw(raw),
            IsInstance(v1beta1.CertificateSigningRequest),
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


    def test_constant_attributes(self):
        """
        The ``apiVersion`` and ``kind`` attributes reflect the Kubernetes object
        apiVersion and kind fields.
        """
        p = v1.Pod()
        self.expectThat(p.apiVersion, Equals(u"v1"))
        self.expectThat(p.kind, Equals(u"Pod"))

        pl = v1.PodList()
        self.expectThat(pl.apiVersion, Equals(u"v1"))
        self.expectThat(pl.kind, Equals(u"PodList"))

        d = v1beta1.Deployment()
        self.expectThat(d.apiVersion, Equals(u"v1beta1"))
        self.expectThat(d.kind, Equals(u"Deployment"))

        dl = v1beta1.DeploymentList()
        self.expectThat(dl.apiVersion, Equals(u"v1beta1"))
        self.expectThat(dl.kind, Equals(u"DeploymentList"))


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


    @given(objectcollections())
    def test_empty_collection(self, collection):
        """
        The ``items`` of a collection can be made empty in a couple different
        ways.
        """
        self.expectThat(collection.set(items=None).items, Equals([]))
        self.expectThat(collection.set(items=[]).items, Equals([]))



    @given(collection=namespacelists(), choose=choices())
    def test_unique_contents(self, collection, choose):
        """
        A collection type cannot contain more than one object with a particular
        namespace / name pair.
        """
        assume(len(collection.items) > 0)
        item = choose(collection.items)
        self.expectThat(
            lambda: collection.add(item),
            raises_exception(InvariantException),
        )


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


    def test_fill_defaults(self):
        """
        ``Namespace.fill_defaults`` returns a ``Namespace`` with *uid* metadata
        and an active *status*.
        """
        # If they are not set already, a uid is generated and put into the
        # metadata and the status is set to active.
        sparse = v1.Namespace(metadata=v1.ObjectMeta(name=u"foo"))
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



class SetIfNoneTests(TestCase):
    """
    Tests for ``set_if_none``.
    """
    def test_none(self):
        """
        If the value for transformation is ``None``, the result contains the new
        value instead.
        """
        structure = freeze({u"foo": None})
        transformed = structure.transform([u"foo"], set_if_none(u"bar"))
        self.assertThat(transformed[u"foo"], Equals(u"bar"))


    def test_not_none(self):
        """
        If the value for transformation is not ``None``, the result contains the
        original value.
        """
        structure = freeze({u"foo": u"baz"})
        transformed = structure.transform([u"foo"], set_if_none(u"bar"))
        self.assertThat(transformed[u"foo"], Equals(u"baz"))
