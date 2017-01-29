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
from twisted.web.http import CREATED

from klein import Klein

from werkzeug.exceptions import NotFound

from eliot import Message

from treq.testing import RequestTraversalAgent

from . import (
    IKubernetes, network_kubernetes,
    NamespaceStatus,
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
            agent=RequestTraversalAgent(self._resource),
        )

    def client(self, *args, **kwargs):
        """
        :return IKubernetesClient: A new client which interacts with this
            object rather than a real Kubernetes deployment.
        """
        return self._kubernetes.client(*args, **kwargs)



def _kubernetes_resource(state):
    return _Kubernetes(state).app.resource()


@attr.s
class _KubernetesState(object):
    namespaces = attr.ib(default=ObjectCollection())
    configmaps = attr.ib(default=ObjectCollection())


def terminate(obj):
    # TODO: Add deletionTimestamp?  See #24
    return obj.transform(
        [u"status"], NamespaceStatus.terminating(),
    )


@attr.s(frozen=True)
class _Kubernetes(object):
    """
    A place to stick a bunch of Klein definitions.

    :ivar _KubernetesState state: The Kubernetes state with which the API will
        be interacting.
    """
    state = attr.ib()

    def _reduce_to_namespace(self, collection, namespace):
        # Unfortunately pset does not support transform. :( Use this more
        # verbose .set() operation.
        return collection.set(
            u"items",
            pset(obj for obj in collection.items if obj.metadata.namespace == namespace),
        )

    def _list(self, request, namespace, collection):
        if namespace is not None:
            collection = self._reduce_to_namespace(collection, namespace)
        request.responseHeaders.setRawHeaders(u"content-type", [u"application/json"])
        return dumps(collection.to_raw())

    def _get(self, request, collection, namespace, name):
        if namespace is not None:
            collection = self._reduce_to_namespace(collection, namespace)
        obj = collection.item_by_name(name)
        request.responseHeaders.setRawHeaders(u"content-type", [u"application/json"])
        return dumps(obj.to_raw())

    def _create(self, request, type, collection, collection_name):
        obj = type.from_raw(loads(request.content.read())).fill_defaults()
        setattr(self.state, collection_name, collection.add(obj))
        request.responseHeaders.setRawHeaders(u"content-type", [u"application/json"])
        request.setResponseCode(CREATED)
        return dumps(obj.to_raw())

    def _delete(self, request, collection, collection_name, name):
        obj = collection.item_by_name(name)
        setattr(self.state, collection_name, collection.replace(obj, terminate(obj)))
        request.responseHeaders.setRawHeaders(u"content-type", [u"application/json"])
        return dumps(obj.to_raw())

    app = Klein()
    @app.handle_errors(NotFound)
    def not_found(self, request, name):
        # XXX Untested - https://github.com/LeastAuthority/txkube/issues/42
        request.responseHeaders.setRawHeaders(u"content-type", [u"application/json"])
        return dumps({u"message": u"boo"})

    with app.subroute(u"/api/v1") as app:
        @app.route(u"/namespaces", methods=[u"GET"])
        def list_namespaces(self, request):
            """
            Get all existing Namespaces.
            """
            return self._list(request, None, self.state.namespaces)

        @app.route(u"/namespaces/<namespace>", methods=[u"GET"])
        def get_namespace(self, request, namespace):
            """
            Get one Namespace by name.
            """
            return self._get(request, self.state.namespaces, None, namespace)

        @app.route(u"/namespaces/<namespace>", methods=[u"DELETE"])
        def delete_namespace(self, request, namespace):
            """
            Delete one Namespace by name.
            """
            return self._delete(
                request, self.state.namespaces, "namespaces", namespace,
            )

        @app.route(u"/namespaces", methods=[u"POST"])
        def create_namespace(self, request):
            """
            Create a new Namespace.
            """
            return self._create(request, Namespace, self.state.namespaces, "namespaces")

        @app.route(u"/configmaps", methods=[u"GET"])
        def list_configmaps(self, request, namespace=None):
            """
            Get all existing ConfigMaps.
            """
            return self._list(request, namespace, self.state.configmaps)

        @app.route(u"/namespaces/<namespace>/configmaps/<configmap>", methods=[u"GET"])
        def get_configmap(self, request, namespace, configmap):
            """
            Get one ConfigMap by name.
            """
            return self._get(request, self.state.configmaps, namespace, configmap)

        @app.route(u"/namespaces/<namespace>/configmaps", methods=[u"POST"])
        def create_configmap(self, request, namespace):
            """
            Create a new ConfigMap.
            """
            return self._create(request, ConfigMap, self.state.configmaps, "configmaps")
