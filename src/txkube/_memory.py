# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
An in-memory implementation of the Kubernetes client interface.
"""

from json import dumps, loads

import attr

from pyrsistent import InvariantException, pset

from zope.interface import implementer

from twisted.python.url import URL

from twisted.python.compat import nativeString
from twisted.web.http import CREATED, CONFLICT, NOT_FOUND, OK

from eliot import start_action

from klein import Klein

from werkzeug.exceptions import NotFound

from treq.testing import RequestTraversalAgent

from . import (
    IKubernetes, network_kubernetes,
    v1, v1beta1,
    iobject_from_raw, iobject_to_raw,
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
    namespaces = attr.ib(default=v1.NamespaceList())
    configmaps = attr.ib(default=v1.ConfigMapList())
    services = attr.ib(default=v1.ServiceList())

    deployments = attr.ib(default=v1beta1.DeploymentList())



def response(request, status, obj):
    """
    Generate a response.

    :param IRequest request: The request being responsed to.
    :param int status: The response status code to set.
    :param obj: Something JSON-dumpable to write into the response body.

    :return bytes: The response body to write out.  eg, return this from a
        *render_* method.
    """
    request.setResponseCode(status)
    request.responseHeaders.setRawHeaders(
        u"content-type", [u"application/json"],
    )
    return dumps(obj)



def _message(details, event):
    if details.get(u"group") is None:
        fmt = u"{kind} \"{name}\" {event}"
    else:
        fmt = u"{kind}.{group} \"{name}\" {event}"
    return fmt.format(event=event, **details)



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
        with start_action(action_type=u"memory:list", kind=collection.kind):
            if namespace is not None:
                collection = self._reduce_to_namespace(collection, namespace)
            return response(request, OK, iobject_to_raw(collection))

    def _get(self, group, request, collection, collection_name, namespace, name):
        if namespace is not None:
            collection = self._reduce_to_namespace(collection, namespace)
        try:
            obj = collection.item_by_name(name)
        except KeyError:
            details = {
                u"name": name,
                u"kind": collection_name,
                u"group": group,
            }
            message = _message(details, u"not found")
            return response(
                request,
                NOT_FOUND,
                iobject_to_raw(v1.Status(
                    status=u"Failure",
                    message=message,
                    reason=u"NotFound",
                    details=details,
                    metadata={},
                    code=NOT_FOUND,
                )),
            )
        else:
            return response(request, OK, iobject_to_raw(obj))

    def _create(self, group, request, collection, collection_name):
        with start_action(action_type=u"memory:create", kind=collection.kind):
            obj = iobject_from_raw(loads(request.content.read())).fill_defaults()
            try:
                added = collection.add(obj)
            except InvariantException:
                details = {
                    u"name": obj.metadata.name,
                    u"kind": collection_name,
                    u"group": group,
                }
                return response(
                    request,
                    CONFLICT,
                    iobject_to_raw(v1.Status(
                        status=u"Failure",
                        message=_message(details, u"already exists"),
                        reason=u"AlreadyExists",
                        details=details,
                        metadata={},
                        code=CONFLICT,
                    )),
                )

            setattr(self.state, nativeString(collection_name), added)
            return response(request, CREATED, iobject_to_raw(obj))

    def _delete(self, request, collection, collection_name, namespace, name):
        if namespace is None:
            obj = collection.item_by_name(name)
        else:
            obj = self._reduce_to_namespace(collection, namespace).item_by_name(name)
        setattr(self.state, collection_name, obj.delete_from(collection))
        return response(request, OK, iobject_to_raw(obj))

    app = Klein()
    @app.handle_errors(NotFound)
    def not_found(self, request, name):
        return response(
            request,
            NOT_FOUND,
            iobject_to_raw(v1.Status(
                status=u"Failure",
                message=u"the server could not find the requested resource",
                reason=u"NotFound",
                details={},
                metadata={},
                code=NOT_FOUND,
            )),
        )

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
            return self._get(None, request, self.state.namespaces, u"namespaces", None, namespace)

        @app.route(u"/namespaces/<namespace>", methods=[u"DELETE"])
        def delete_namespace(self, request, namespace):
            """
            Delete one Namespace by name.
            """
            return self._delete(
                request, self.state.namespaces, "namespaces", None, namespace,
            )

        @app.route(u"/namespaces", methods=[u"POST"])
        def create_namespace(self, request):
            """
            Create a new Namespace.
            """
            return self._create(None, request, self.state.namespaces, u"namespaces")

        @app.route(u"/configmaps", methods=[u"GET"])
        def list_configmaps(self, request):
            """
            Get all existing ConfigMaps.
            """
            return self._list(request, None, self.state.configmaps)

        @app.route(u"/namespaces/<namespace>/configmaps/<configmap>", methods=[u"GET"])
        def get_configmap(self, request, namespace, configmap):
            """
            Get one ConfigMap by name.
            """
            return self._get(None, request, self.state.configmaps, u"configmaps", namespace, configmap)

        @app.route(u"/namespaces/<namespace>/configmaps", methods=[u"POST"])
        def create_configmap(self, request, namespace):
            """
            Create a new ConfigMap.
            """
            return self._create(None, request, self.state.configmaps, u"configmaps")

        @app.route(u"/namespaces/<namespace>/configmaps/<configmap>", methods=[u"DELETE"])
        def delete_configmap(self, request, namespace, configmap):
            """
            Delete one ConfigMap by name.
            """
            return self._delete(
                request, self.state.configmaps, "configmaps", namespace, configmap,
            )

        @app.route(u"/namespaces/<namespace>/services", methods=[u"POST"])
        def create_service(self, request, namespace):
            """
            Create a new Service.
            """
            return self._create(None, request, self.state.services, u"services")

        @app.route(u"/services", methods=[u"GET"])
        def list_services(self, request):
            """
            Get all existing Services.
            """
            return self._list(request, None, self.state.services)

        @app.route(u"/namespaces/<namespace>/services/<service>", methods=[u"GET"])
        def get_service(self, request, namespace, service):
            """
            Get one Service by name.
            """
            return self._get(
                None,
                request,
                self.state.services,
                u"services",
                namespace,
                service,
            )

        @app.route(u"/namespaces/<namespace>/services/<service>", methods=[u"DELETE"])
        def delete_service(self, request, namespace, service):
            """
            Delete one Service by name.
            """
            return self._delete(
                request, self.state.services, "services", namespace, service,
            )

    with app.subroute(u"/apis/extensions/v1beta1") as app:
        @app.route(u"/namespaces/<namespace>/deployments", methods=[u"POST"])
        def create_deployment(self, request, namespace):
            """
            Create a new Deployment.
            """
            return self._create(
                u"extensions",
                request,
                self.state.deployments,
                u"deployments",
            )

        @app.route(u"/deployments", methods=[u"GET"])
        def list_deployments(self, request):
            """
            Get all existing Deployments.
            """
            return self._list(request, None, self.state.deployments)

        @app.route(u"/namespaces/<namespace>/deployments/<deployment>", methods=[u"GET"])
        def get_deployment(self, request, namespace, deployment):
            """
            Get one Deployment by name.
            """
            return self._get(
                u"extensions",
                request,
                self.state.deployments,
                u"deployments",
                namespace,
                deployment,
            )

        @app.route(u"/namespaces/<namespace>/deployments/<deployment>", methods=[u"DELETE"])
        def delete_deployment(self, request, namespace, deployment):
            """
            Delete one Deployment by name.
            """
            return self._delete(
                request, self.state.deployments, "deployments", namespace, deployment,
            )
