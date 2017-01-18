# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
An in-memory implementation of the Kubernetes client interface.
"""

from functools import partial

from json import dumps, loads

import attr

from pyrsistent import pset

from zope.interface import implementer

from twisted.python.url import URL

from twisted.web.resource import Resource, NoResource

from eliot import Message

from treq.testing import RequestTraversalAgent

from . import (
    IKubernetes, network_kubernetes,
    ObjectCollection, Namespace, ConfigMap,
)


def memory_kubernetes():
    """
    Create an in-memory Kubernetes-alike service.

    This serves as a places to hold state for stateful Kubernetes interactions
    allowed by ``IKubernetesClient``.  Only clients created against the same
    instance will all share state.

    :return IKubernetes: The new Kubernetes-alike service.
    """
    return _MemoryKubernetes()


@implementer(IKubernetes)
class _MemoryKubernetes(object):
    """
    ``_MemoryKubernetes`` maintains state in-memory which approximates
    the state of a real Kubernetes deployment sufficiently to expose a
    subset of the external Kubernetes API.
    """
    def __init__(self):
        base_url = URL.fromText(u"https://kubernetes.example.invalid./")
        self._state = _KubernetesState()
        self._resource = _kubernetes_resource(self._state)
        self._kubernetes = network_kubernetes(
            base_url=base_url,
            credentials=None,
            agent=RequestTraversalAgent(self._resource),
        )

    def client(self, *args, **kwargs):
        """
        :return IKubernetesClient: A new client which interacts with this
            object rather than a real Kubernetes deployment.
        """
        return self._kubernetes.client(*args, **kwargs)



@attr.s
class _KubernetesState(object):
    namespaces = attr.ib(default=ObjectCollection())
    configmaps = attr.ib(default=ObjectCollection())


def _kubernetes_resource(state):
    v1 = v1_root(state)

    api = Resource()
    api.putChild(b"v1", v1)

    root = Resource()
    root.putChild(b"api", api)

    return root


def v1_root(state):
    v1 = Resource()
    for model in [Namespace]:
        collection_name = model.kind.lower() + u"s"
        segment = collection_name.encode("ascii")
        get_collection = lambda: getattr(state, collection_name)
        set_collection = lambda value: setattr(state, collection_name, value)
        collection = CollectionV1(
            model.kind, model, get_collection, set_collection, partial(NamespaceV1, state=state),
        )
        v1.putChild(segment, collection)
    return v1


class CollectionV1(Resource):
    def __init__(self, kind, kind_type, get_collection, set_collection, object_resource_type):
        Resource.__init__(self)
        self.putChild(b"", self)
        self._kind = kind
        self._kind_type = kind_type
        self._get_collection = get_collection
        self._set_collection = set_collection
        self._object_resource_type = object_resource_type

    def render_GET(self, request):
        return dumps(self._get_collection().to_raw())

    def render_POST(self, request):
        obj = self._kind_type.from_raw(loads(request.content.read()))
        self._set_collection(self._get_collection().add(obj))
        request.method = b"GET"
        return self.getChild(obj.metadata.name, request).render(request)

    def getChild(self, name, request):
        try:
            obj = self._get_collection().item_by_name(name)
        except KeyError:
            Message.log(get_child=u"CollectionV1", name=name, found=False)
            return NoResource()
        Message.log(get_child=u"CollectionV1", name=name, found=True)
        return self._object_resource_type(obj)


class ObjectV1(Resource):
    def __init__(self, obj):
        Resource.__init__(self)
        self._obj = obj

    def render_GET(self, request):
        return dumps(self._obj.to_raw())


class NamespaceV1(ObjectV1):
    def __init__(self, obj, state):
        ObjectV1.__init__(self, obj)
        self._state = state


    def getChild(self, name, request):
        Message.log(get_child=u"NamespaceV1", name=name, found=True)
        get_collection = lambda: getattr(self._state, name)
        set_collection = lambda value: setattr(self._state, name, value)
        return NamespacedCollectionV1(self._obj.metadata.name, get_collection, set_collection)


class NamespacedCollectionV1(Resource):
    def __init__(self, namespace, get_collection, set_collection):
        Resource.__init__(self)
        self.putChild(b"", self)
        self._namespace = namespace
        self._get_collection = get_collection
        self._set_collection = set_collection


    def getChild(self, name, request):
        try:
            obj = self._get_collection().item_by_name(name)
        except KeyError:
            Message.log(get_child=u"NamespacedCollectionV1", name=name, found=False)
            return NoResource()
        Message.log(get_child=u"NamespacedCollectionV1", name=name, found=True)
        return ObjectV1(obj)


    def render_POST(self, request):
        obj = Namespace.from_raw(loads(request.content.read()))
        self._set_collection(self._get_collection().add(obj))
        request.method = b"GET"
        return self.getChild(obj.metadata.name, request).render(request)


    def render_GET(self):
        objects = (
            obj
            for obj
            in self._get_collection().items
            if obj.metadata.namespace == self._namespace
        )
        return dumps(ObjectCollection(items=objects).to_raw())
