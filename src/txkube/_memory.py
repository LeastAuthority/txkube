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
    """
    Create the /api/v1 resource.
    """
    v1 = Resource()

    collection_name = Namespace.kind.lower() + u"s"
    segment = collection_name.encode("ascii")
    collection = CollectionV1(
        Namespace.kind, Namespace, state, partial(NamespaceV1, state=state),
    )
    v1.putChild(segment, collection)

    collection_name = ConfigMap.kind.lower() + u"s"
    segment = collection_name.encode("ascii")
    collection = CollectionV1(
        ConfigMap.kind, ConfigMap, state, ObjectV1,
    )
    v1.putChild(segment, collection)

    return v1


class CollectionV1(Resource):
    """
    A resource which serves a collection of Kubernetes objects.

    For example, /api/v1/namespaces or /api/v1/configmaps.
    """
    def __init__(self, kind, kind_type, state, object_resource_type):
        Resource.__init__(self)
        self.putChild(b"", self)
        self._kind = kind
        self._collection_kind = kind.lower() + u"s"
        self._kind_type = kind_type
        self._state = state
        self._object_resource_type = object_resource_type

    def getChild(self, name, request):
        try:
            obj = getattr(self._state, self._collection_kind).item_by_name(name)
        except KeyError:
            Message.log(get_child=u"CollectionV1", name=name, found=False)
            return NoResource()
        Message.log(get_child=u"CollectionV1", name=name, found=True)
        return self._object_resource_type(obj)

    def render_GET(self, request):
        return dumps(getattr(self._state, self._collection_kind).to_raw())

    def render_POST(self, request):
        obj = self._kind_type.from_raw(loads(request.content.read()))
        setattr(self._state, self._collection_kind, getattr(self._state, self._collection_kind).add(obj))
        request.method = b"GET"
        return self.getChild(obj.metadata.name, request).render(request)


class ObjectV1(Resource):
    """
    A resource which serves a single Kubernetes object.

    For example, /api/v1/secrets/default-token-foo (but not /api/v1/namespaces/default).
    """
    def __init__(self, obj):
        Resource.__init__(self)
        self._obj = obj

    def render_GET(self, request):
        return dumps(self._obj.to_raw())


class NamespaceV1(ObjectV1):
    """
    A resource which serves a single Kubernetes namespace.

    eg /api/v1/namespaces/default
    """
    def __init__(self, obj, state):
        ObjectV1.__init__(self, obj)
        self._state = state


    def getChild(self, name, request):
        Message.log(get_child=u"NamespaceV1", name=name, found=True)
        return NamespacedCollectionV1(self._obj.metadata.name, self._state, name)


class NamespacedCollectionV1(Resource):
    """
    A resource which serves a collection of Kubernetes objects which belong to
    a particular namespace.

    eg /api/v1/namespaces/default/configmaps
    """
    def __init__(self, namespace, state, kind):
        Resource.__init__(self)
        self.putChild(b"", self)
        self._namespace = namespace
        self._state = state
        self._kind = kind


    def getChild(self, name, request):
        try:
            obj = getattr(self._state, self._kind).item_by_name(name)
        except KeyError:
            Message.log(get_child=u"NamespacedCollectionV1", name=name, found=False)
            return NoResource()
        Message.log(get_child=u"NamespacedCollectionV1", name=name, found=True)
        return ObjectV1(obj)


    def render_POST(self, request):
        obj = Namespace.from_raw(loads(request.content.read()))
        setattr(self._state, self._kind, getattr(self._state, self._kind).add(obj))
        request.method = b"GET"
        return self.getChild(obj.metadata.name, request).render(request)


    def render_GET(self):
        objects = (
            obj
            for obj
            in getatr(self._state, self._kind).items
            if obj.metadata.namespace == self._namespace
        )
        return dumps(ObjectCollection(items=objects).to_raw())
