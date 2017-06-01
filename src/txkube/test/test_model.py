# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube._model``.
"""

from json import loads, dumps

from zope.interface import implementer
from zope.interface.verify import verifyObject

import attr

from pyrsistent import (
    InvariantException,
    freeze,
)

from testtools.matchers import (
    NotEquals,
    Equals,
    LessThan,
    GreaterThan,
    MatchesStructure,
    Not,
    Is,
    Contains,
    ContainsAll,
    raises,
    IsInstance,
)
from testtools.twistedsupport import succeeded

from hypothesis import HealthCheck, settings, given, assume
from hypothesis.strategies import sampled_from, choices

from twisted.python.failure import Failure
from twisted.internet.defer import gatherResults
from twisted.web.iweb import IResponse
from twisted.web.http_headers import Headers
from twisted.web.client import ResponseDone

from ..testing import TestCase
from ..testing.matchers import (
    PClassEquals,
    EqualElements,
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
    KubernetesError,
    IObject,
    v1_5_model, openapi_to_data_model,
)

from .._model import set_if_none



def models():
    return sampled_from([v1_5_model])



class SerializationTests(TestCase):
    """
    Tests for ``iobject_to_raw`` and ``iobject_from_raw``.
    """
    def test_v1_apiVersion(self):
        """
        Objects from ``v1`` serialize with an *apiVersion* of ``u"v1"``.
        """
        model = v1_5_model

        obj = model.v1.ComponentStatus()
        raw = model.iobject_to_raw(obj)
        self.expectThat(
            raw[u"apiVersion"],
            Equals(u"v1"),
        )
        self.expectThat(
            model.iobject_from_raw(raw),
            IsInstance(model.v1.ComponentStatus),
        )


    def test_v1beta1_apiVersion(self):
        """
        Objects from ``v1beta1`` serialize with an *apiVersion* of
        ``u"extensions/v1beta1"``.
        """
        model = v1_5_model

        obj = model.v1beta1.CertificateSigningRequest()
        raw = model.iobject_to_raw(obj)
        self.expectThat(
            raw[u"apiVersion"],
            Equals(u"extensions/v1beta1"),
        )
        self.expectThat(
            model.iobject_from_raw(raw),
            IsInstance(model.v1beta1.CertificateSigningRequest),
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


    @given(models())
    def test_constant_attributes(self, model):
        """
        The ``apiVersion`` and ``kind`` attributes reflect the Kubernetes object
        apiVersion and kind fields.
        """
        p = model.v1.Pod()
        self.expectThat(p.apiVersion, Equals(u"v1"))
        self.expectThat(p.kind, Equals(u"Pod"))

        pl = model.v1.PodList()
        self.expectThat(pl.apiVersion, Equals(u"v1"))
        self.expectThat(pl.kind, Equals(u"PodList"))

        d = model.v1beta1.Deployment()
        self.expectThat(d.apiVersion, Equals(u"v1beta1"))
        self.expectThat(d.kind, Equals(u"Deployment"))

        dl = model.v1beta1.DeploymentList()
        self.expectThat(dl.apiVersion, Equals(u"v1beta1"))
        self.expectThat(dl.kind, Equals(u"DeploymentList"))


    @given(obj=iobjects())
    def test_serialization_roundtrip(self, obj):
        """
        An ``IObject`` provider can be round-trip through JSON using
        ``iobject_to_raw`` and ``iobject_from_raw``.
        """
        model = v1_5_model

        marshalled = model.iobject_to_raw(obj)

        # Every IObject has these marshalled fields - and when looking at the
        # marshalled form, they're necessary to figure out the
        # schema/definition for the data.  We can't say anything in general
        # about the *values* (because of things like "extensions/v1beta1") but
        # we can at least assert the keys are present.
        self.expectThat(marshalled, ContainsAll([u"kind", u"apiVersion"]))

        # We should be able to unmarshal the data back to the same model
        # object as we started with.
        reloaded = model.iobject_from_raw(marshalled)
        self.expectThat(obj, PClassEquals(reloaded))

        # And, to be extra sure (ruling out any weird Python object
        # semantic hijinx), that that reconstituted object should marshal
        # back to exactly the same simplified object graph.
        remarshalled = model.iobject_to_raw(reloaded)
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
        model = v1_5_model

        obj = {
            u"apiVersion": u"invalid.example.txkube",
            u"kind": u"Service",
        }
        self.assertThat(
            lambda: model.iobject_from_raw(obj),
            raises(UnrecognizedVersion(obj[u"apiVersion"], obj)),
        )


    def test_unknown_kind(self):
        """
        ``iobject_from_raw`` raises ``UnrecognizedKind`` if it does not recognize
        the *kind* in the given data.
        """
        model = v1_5_model

        obj = {
            u"apiVersion": u"v1",
            u"kind": u"SomethingFictional",
        }
        self.assertThat(
            lambda: model.iobject_from_raw(obj),
            raises(UnrecognizedKind(u"v1", u"SomethingFictional", obj)),
        )



class NamespaceTests(TestCase):
    """
    Other tests for ``Namespace``.
    """
    @given(models())
    def test_default(self, model):
        """
        ``Namespace.default`` returns the *default* namespace.
        """
        self.assertThat(
            model.v1.Namespace.default(),
            MatchesStructure(
                metadata=MatchesStructure(
                    name=Equals(u"default"),
                ),
            ),
        )


    @given(models())
    def test_fill_defaults(self, model):
        """
        ``Namespace.fill_defaults`` returns a ``Namespace`` with *uid* metadata
        and an active *status*.
        """
        # If they are not set already, a uid is generated and put into the
        # metadata and the status is set to active.
        sparse = model.v1.Namespace(metadata=model.v1.ObjectMeta(name=u"foo"))
        filled = sparse.fill_defaults()
        self.expectThat(
            filled,
            MatchesStructure(
                metadata=MatchesStructure(
                    uid=Not(Is(None)),
                ),
                status=Equals(model.v1.NamespaceStatus.active()),
            ),
        )



class NamespaceListTests(TestCase):
    """
    Tests for ``NamespaceList``.
    """
    @settings(suppress_health_check=[HealthCheck.exception_in_generation])
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

    @given(collection=namespacelists(), choose=choices())
    def test_no_duplicates(self, collection, choose):
        assume(len(collection.items) > 0)
        self.expectThat(
            lambda: collection.add(choose(collection.items)),
            raises_exception(InvariantException),
        )


    @given(collection=namespacelists())
    def test_constant_attributes(self, collection):
        self.expectThat(collection.kind, Equals(u"NamespaceList"))
        self.expectThat(collection.apiVersion, Equals(u"v1"))



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



@implementer(IResponse)
@attr.s
class MemoryResponse(object):
    version = attr.ib()
    code = attr.ib()
    phrase = attr.ib()
    headers = attr.ib()
    length = attr.ib()

    request = attr.ib()
    previousResponse = attr.ib()

    _body = attr.ib()

    def deliverBody(self, protocol):
        protocol.makeConnection(None)
        protocol.dataReceived(self._body)
        protocol.connectionLost(Failure(ResponseDone()))



class KubernetesErrorTests(TestCase):
    """
    Tests for ``KubernetesError``.
    """
    def test_from_response(self):
        """
        ``from_response`` returns the same value as ``from_model_and_response``
        when called with the v1.5 model.
        """
        def response():
            body = dumps(v1_5_model.iobject_to_raw(v1_5_model.v1.Status()))
            return MemoryResponse(
                version=(b"HTTP", 1, 1),
                code=200,
                phrase=b"OK",
                headers=Headers(),
                length=len(body),
                request=None,
                previousResponse=None,
                body=body,
            )

        ds = gatherResults([
            KubernetesError.from_response(response()),
            KubernetesError.from_model_and_response(v1_5_model, response()),
        ])
        self.assertThat(
            ds,
            succeeded(EqualElements()),
        )


    def test_comparison(self):
        """
        The binary comparison operations work on ``KubernetesError`` as expected.
        """
        model = v1_5_model

        a1 = KubernetesError(200, model.v1.Status(status=u"A"))
        a2 = KubernetesError(200, model.v1.Status(status=u"A"))
        b = KubernetesError(201, model.v1.Status(status=u"A"))
        c = KubernetesError(200, model.v1.Status(status=u"B"))

        # a1 == a2
        self.expectThat(a1, Equals(a2))
        # not (a1 != a2)
        self.expectThat(a1, Not(NotEquals(a2)))
        # not (a1 > a2)
        self.expectThat(a1, Not(GreaterThan(a2)))
        # not (a1 < a2)
        self.expectThat(a1, Not(LessThan(a2)))

        # not (a1 == b)
        self.expectThat(a1, Not(Equals(b)))
        # a1 != b
        self.expectThat(a1, NotEquals(b))
        # a1 < b
        self.expectThat(a1, LessThan(b))
        # not (a1 > b)
        self.expectThat(a1, Not(GreaterThan(b)))

        # not (a1 == c)
        self.expectThat(a1, Not(Equals(b)))
        # a1 != c
        self.expectThat(a1, NotEquals(b))
        # a1 < c
        self.expectThat(a1, LessThan(c))
        # not (a1 > c)
        self.expectThat(a1, Not(GreaterThan(c)))

        @attr.s
        class Comparator(object):
            result = attr.ib()

            def __cmp__(self, other):
                return self.result

        largest = Comparator(1)
        equalest = Comparator(0)
        smallest = Comparator(-1)

        # a1 < largest
        self.expectThat(a1, LessThan(largest))
        # a1 == equalest
        self.expectThat(a1, Equals(equalest))
        # a1 > smallest
        self.expectThat(a1, GreaterThan(smallest))



class Extra15DataModelTests(TestCase):
    """
    Tests for handling of certain Kubernetes 1.5 Swagger specifications.
    """
    def test_status(self):
        """
        If the Kubernetes-reported Swagger specification is missing the Status
        definitions, ``openapi_to_data_model`` returns a data model that
        defines them anyway.
        """
        openapi = v1_5_model.spec.to_document()
        openapi[u"definitions"].clear()
        model = openapi_to_data_model(openapi)
        model.v1.Status
        model.v1.StatusCause
        model.v1.StatusDetails
        model.v1.ListMeta
