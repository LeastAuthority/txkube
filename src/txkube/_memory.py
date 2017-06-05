# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
An in-memory implementation of the Kubernetes client interface.
"""

from json import dumps, loads

import attr

from pyrsistent import InvariantException, PClass, field, pset

from zope.interface import Interface, implementer

from twisted.python.url import URL

from twisted.web.http import CREATED, NOT_FOUND, OK

from eliot import start_action

from klein import Klein

from werkzeug.exceptions import NotFound

from treq.testing import RequestTraversalAgent

from . import (
    IKubernetes, KubernetesError, network_kubernetes,
    v1_5_model,
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

    :ivar model: All of the Kubernetes model objects as understood by this
        service.
    """
    def __init__(self):
        base_url = URL.fromText(u"https://kubernetes.example.invalid./")
        self.model = v1_5_model
        self._state = _KubernetesState.for_model(self.model)
        self._resource = _kubernetes_resource(self, self.model)
        self._kubernetes = network_kubernetes(
            base_url=base_url,
            agent=RequestTraversalAgent(self._resource),
        )


    def _state_changed(self, state):
        """
        The Kubernetes state has been changed.  Record the new version.

        The state is immutable so any changes must be represented as a brand
        new object.

        :param _KubernetesState state: The new state.
        """
        self._state = state


    def versioned_client(self, *args, **kwargs):
        """
        :return IKubernetesClient: A new client which interacts with this
            object rather than a real Kubernetes deployment.
        """
        return self._kubernetes.versioned_client(*args, **kwargs)


    def client(self, *args, **kwargs):
        """
        :return IKubernetesClient: A new client which interacts with this
            object rather than a real Kubernetes deployment.
        """
        return self._kubernetes.client(*args, **kwargs)



def _kubernetes_resource(memory_service, model):
    return _Kubernetes(memory_service, model).app.resource()



def _incrementResourceVersion(version):
    """
    Pyrsistent transformation function which can increment a
    ``v1.ObjectMeta.resourceVersion`` value (even if it was missing).

    :param version: The old version as a ``unicode`` string or ``None`` if
        there wasn't one.

    :return unicode: The new version, guaranteed to be greater than the old
        one.
    """
    if version is None:
        version = 0
    return u"{}".format(int(version) + 1)



def _transform_object(obj, *transformation):
    """
    Apply a pyrsistent transformation to an ``IObject``.

    In addition to the given transformation, the object's resourceVersion will
    be updated.

    :param IObject: obj: The object to transform.
    :param *transformation: Arguments like those to ``PClass.transform``.

    :return: The transformed object.
    """
    return obj.transform(
        [u"metadata", u"resourceVersion"],
        _incrementResourceVersion,
        *transformation
    )



def _api_group_for_type(cls):
    """
    Determine which Kubernetes API group a particular PClass is likely to
    belong with.

    This is basically nonsense.  The question being asked is wrong.  An
    abstraction has failed somewhere.  Fixing that will get rid of the need
    for this.
    """
    _groups = {
        (u"v1beta1", u"Deployment"): u"extensions",
        (u"v1beta1", u"DeploymentList"): u"extensions",
        (u"v1beta1", u"ReplicaSet"): u"extensions",
        (u"v1beta1", u"ReplicaSetList"): u"extensions",
    }
    key = (
        cls.apiVersion,
        cls.__name__.rsplit(u".")[-1],
    )
    group = _groups.get(key, None)
    return group



class IAgency(Interface):
    """
    An ``IAgency`` implementation can impress certain additional behaviors
    upon a ``_KubernetesState``.  The latter shall use methods of the former
    during state changes to give the former an opportunity to influence the
    outcome of the state change.
    """
    def before_create(state, obj):
        """
        This is called before an object is created.

        :param _KubernetesState state: The state in which the object is being
            created.

        :param IObject obj: A description of the object to be created.

        :return IObject: The object to really create.  Typically this is some
            transformation of ``obj`` (for example, with default values
            populated).
        """


    def after_create(state, obj):
        """
        This is called after an object has been created.

        :param _KubernetesState state: The state in which the object is being
            created.

        :param IObject obj: A description of the object created.  Regardless
            of the implementation of this method, this is the description
            which will be returned in the response to the create operation.

        :return IObject: The object to store in the state.  Typically this is
            some transformation of ``obj`` (for example, with an observed
            status attached)l.
        """


    def before_replace(state, old, new):
        """
        This is called before an existing object is replaced by a new one.

        :param _KubernetesState state: The state in which the object is being
            replaced.

        :param IObject old: A description of the object being replaced.

        :param IObject new: A description of the object to replace ``old``.

        :raise: Some exception to prevent the replacement from taking place.

        :return: ``None``
        """



@implementer(IAgency)
class NullAgency(object):
    """
    ``NullAgency`` does nothing.
    """
    def before_create(self, state, obj):
        return obj


    def after_create(self, state, obj):
        return obj


    def before_replace(self, state, old, new):
        pass



@implementer(IAgency)
@attr.s(frozen=True)
class AdHocAgency(object):
    """
    ``AdHocAgency`` implements some object changes which I observed to happen
    on a real Kubernetes server while I was working on various parts of
    txkube.  No attempt at completeness attempted.  The system for selecting
    changes to implement is to run into important inconsistencies between this
    and a real Kubernetes while developing other features and then fix those
    inconsistencies.

    Perhaps in the future this will be replaced by something with less of an
    ad hoc nature.
    """
    model = attr.ib()

    def before_create(self, state, obj):
        return obj.fill_defaults()


    def after_create(self, state, obj):
        if isinstance(obj, self.model.v1beta1.Deployment):
            obj = _transform_object(
                obj,
                [u"metadata", u"annotations", u"deployment.kubernetes.io/revision"],
                u"1",
                [u"status"],
                {},
                [u"status", u"observedGeneration"],
                1,
                [u"status", u"unavailableReplicas"],
                1,
            )
        return obj


    def before_replace(self, state, old, new):
        if old.metadata.resourceVersion != new.metadata.resourceVersion:
            group = _api_group_for_type(type(old))
            details = {
                u"group": group,
                u"kind": old.kind,
                u"name": old.metadata.name,
            }
            raise KubernetesError.object_modified(details)


class _KubernetesState(PClass):
    """
    ``_KubernetesState`` contains the canonical representation of internal
    state required to emulate a Kubernetes server.

    :ivar IAgency agency: Any behavior to apply to transformations of this
        state.
    """
    agency = field()

    namespaces = field()
    configmaps = field()
    services = field()
    pods = field()

    deployments = field()
    replicasets = field()


    @classmethod
    def for_model(cls, model):
        return cls(
            agency=AdHocAgency(model=model),

            namespaces=model.v1.NamespaceList(),
            configmaps=model.v1.ConfigMapList(),
            services=model.v1.ServiceList(),
            pods=model.v1.PodList(),

            deployments=model.v1beta1.DeploymentList(),
            replicasets=model.v1beta1.ReplicaSetList(),
        )

    def create(self, collection_name, obj):
        """
        Create a new object in the named collection.

        :param unicode collection_name: The name of the collection in which to
            create the object.

        :param IObject obj: A description of the object to create.

        :return _KubernetesState: A new state based on the current state but
            also containing ``obj``.
        """
        obj = self.agency.before_create(self, obj)
        new = self.agency.after_create(self, obj)
        updated = self.transform(
            [collection_name],
            lambda c: c.add(new),
        )
        return updated


    def replace(self, collection_name, old, new):
        """
        Replace an existing object with a new version of it.

        :param unicode collection_name: The name of the collection in which to
            replace an object.

        :param IObject old: A description of the object being replaced.

        :param IObject new: A description of the object to take the place of
            ``old``.

        :return _KubernetesState: A new state based on the current state but
            also containing ``obj``.
        """
        self.agency.before_replace(self, old, new)
        updated = self.transform(
            [collection_name],
            lambda c: c.replace(old, new),
        )
        return updated


    def delete(self, collection_name, obj):
        """
        Delete an existing object.

        :param unicode collection_name: The name of the collection from which
            to delete the object.

        :param IObject obj: A description of the object to delete.

        :return _KubernetesState: A new state based on the current state but
            not containing ``obj``.
        """
        updated = self.transform(
            [collection_name],
            lambda c: obj.delete_from(c),
        )
        return updated



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



@attr.s(frozen=True)
class _Kubernetes(object):
    """
    A place to stick a bunch of Klein definitions.

    :ivar _MemoryKubernetes service: The Kubernetes-alike holding the
        in-memory Kubernetes state with which the API will be interacting.

    :ivar model: All of the Kubernetes model objects as understood by this
        service.
    """
    service = attr.ib()
    model = attr.ib()

    # This could be a property except
    # https://github.com/hynek/attrs/issues/144
    def _get_state(self):
        return self.service._state

    def _set_state(self, value):
        self.service._state_changed(value)

    def _reduce_to_namespace(self, collection, namespace):
        # Unfortunately pset does not support transform. :( Use this more
        # verbose .set() operation.
        return collection.set(
            u"items",
            pset(obj for obj in collection.items if obj.metadata.namespace == namespace),
        )

    def _collection_by_name(self, collection_name):
        return getattr(self._get_state(), collection_name)

    def _list(self, request, namespace, collection_name):
        with start_action(action_type=u"memory:list", kind=collection_name):
            collection = self._collection_by_name(collection_name)
            if namespace is not None:
                collection = self._reduce_to_namespace(collection, namespace)
            return response(request, OK, self.model.iobject_to_raw(collection))

    def _get(self, request, collection_name, namespace, name):
        collection = self._collection_by_name(collection_name)
        if namespace is not None:
            collection = self._reduce_to_namespace(collection, namespace)
        try:
            obj = collection.item_by_name(name)
        except KeyError:
            raise KubernetesError.not_found({
                u"name": name,
                u"kind": collection_name,
                u"group": _api_group_for_type(type(collection))

            })
        return response(request, OK, self.model.iobject_to_raw(obj))

    def _create(self, request, collection_name):
        with start_action(action_type=u"memory:create", kind=collection_name):
            obj = self.model.iobject_from_raw(loads(request.content.read()))
            try:
                state = self._get_state().create(collection_name, obj)
            except InvariantException:
                collection = getattr(self._get_state(), collection_name)
                details = {
                    u"name": obj.metadata.name,
                    u"kind": collection_name,
                    u"group": _api_group_for_type(type(collection)),
                }
                raise KubernetesError.already_exists(details)
            self._set_state(state)
            return response(request, CREATED, self.model.iobject_to_raw(obj))

    def _replace(self, request, collection_name, namespace, name):
        collection = self._collection_by_name(collection_name)
        if namespace is not None:
            collection = self._reduce_to_namespace(collection, namespace)
        old = collection.item_by_name(name)
        new = self.model.iobject_from_raw(loads(request.content.read()))
        try:
            state = self._get_state().replace(collection_name, old, new)
        except KubernetesError as e:
            return response(request, e.code, self.model.iobject_to_raw(e.status))

        self._set_state(state)
        return response(request, OK, self.model.iobject_to_raw(new))

    def _delete(self, request, collection_name, namespace, name):
        collection = self._collection_by_name(collection_name)
        if namespace is not None:
            collection = self._reduce_to_namespace(collection, namespace)
        try:
            obj = collection.item_by_name(name)
        except KeyError:
            raise KubernetesError.not_found({
                u"group": _api_group_for_type(type(collection)),
                u"kind": collection_name,
                u"name": name,
            })
        self._set_state(self._get_state().delete(collection_name, obj))
        return response(request, OK, self.model.iobject_to_raw(obj))

    app = Klein()
    @app.handle_errors(NotFound)
    def not_found(self, request, name):
        return response(
            request,
            NOT_FOUND,
            self.model.iobject_to_raw(self.model.v1.Status(
                status=u"Failure",
                message=u"the server could not find the requested resource",
                reason=u"NotFound",
                details={},
                metadata={},
                code=NOT_FOUND,
            )),
        )

    @app.handle_errors(KubernetesError)
    def object_not_found(self, request, reason):
        exc = reason.value
        return response(request, exc.code, self.model.iobject_to_raw(exc.status))

    @app.route(u"/version", methods=[u"GET"])
    def get_version(self, request):
        """
        Get version information about this server.
        """
        return response(request, OK, self.model.version.serialize())

    @app.route(u"/swagger.json", methods=[u"GET"])
    def get_openapi(self, request):
        """
        Get the OpenAPI specification for this server.
        """
        return response(request, OK, self.model.spec.to_document())

    with app.subroute(u"/api/v1") as app:
        @app.route(u"/namespaces", methods=[u"GET"])
        def list_namespaces(self, request):
            """
            Get all existing Namespaces.
            """
            return self._list(request, None, u"namespaces")

        @app.route(u"/namespaces/<namespace>", methods=[u"GET"])
        def get_namespace(self, request, namespace):
            """
            Get one Namespace by name.
            """
            return self._get(request, u"namespaces", None, namespace)

        @app.route(u"/namespaces/<namespace>", methods=[u"DELETE"])
        def delete_namespace(self, request, namespace):
            """
            Delete one Namespace by name.
            """
            return self._delete(
                request, u"namespaces", None, namespace,
            )

        @app.route(u"/namespaces", methods=[u"POST"])
        def create_namespace(self, request):
            """
            Create a new Namespace.
            """
            return self._create(request, u"namespaces")

        @app.route(u"/namespaces/<namespace>", methods=[u"PUT"])
        def replace_namespace(self, request, namespace):
            """
            Replace an existing Namespace.
            """
            return self._replace(
                request,
                u"namespaces",
                None,
                namespace,
            )

        @app.route(u"/namespaces/<namespace>/pods", methods=[u"POST"])
        def create_pod(self, request, namespace):
            """
            Create a new Pod.
            """
            return self._create(request, u"pods")

        @app.route(u"/namespaces/<namespace>/pods/<pod>", methods=[u"DELETE"])
        def delete_pod(self, request, namespace, pod):
            """
            Delete one Pod by name
            """
            return self._delete(request, u"pods", namespace, pod)

        @app.route(u"/pods", methods=[u"GET"])
        def list_pods(self, request):
            """
            Get all existing Pods.
            """
            return self._list(request, None, u"pods")

        @app.route(u"/namespaces/<namespace>/pods/<pod>", methods=[u"PUT"])
        def replace_pod(self, request, namespace, pod):
            """
            Replace an existing Pod.
            """
            return self._replace(request, u"pods", namespace, pod)

        @app.route(u"/namespaces/<namespace>/pods/<pod>", methods=[u"GET"])
        def get_pod(self, request, namespace, pod):
            """
            Get one Pod by name.
            """
            return self._get(request, u"pods", namespace, pod)

        @app.route(u"/configmaps", methods=[u"GET"])
        def list_configmaps(self, request):
            """
            Get all existing ConfigMaps.
            """
            return self._list(request, None, u"configmaps")

        @app.route(u"/namespaces/<namespace>/configmaps/<configmap>", methods=[u"GET"])
        def get_configmap(self, request, namespace, configmap):
            """
            Get one ConfigMap by name.
            """
            return self._get(request, u"configmaps", namespace, configmap)

        @app.route(u"/namespaces/<namespace>/configmaps", methods=[u"POST"])
        def create_configmap(self, request, namespace):
            """
            Create a new ConfigMap.
            """
            return self._create(request, u"configmaps")

        @app.route(u"/namespaces/<namespace>/configmaps/<configmap>", methods=[u"PUT"])
        def replace_configmap(self, request, namespace, configmap):
            """
            Replace an existing ConfigMap.
            """
            return self._replace(
                request,
                u"configmaps",
                namespace,
                configmap,
            )

        @app.route(u"/namespaces/<namespace>/configmaps/<configmap>", methods=[u"DELETE"])
        def delete_configmap(self, request, namespace, configmap):
            """
            Delete one ConfigMap by name.
            """
            return self._delete(
                request, u"configmaps", namespace, configmap,
            )

        @app.route(u"/namespaces/<namespace>/services", methods=[u"POST"])
        def create_service(self, request, namespace):
            """
            Create a new Service.
            """
            return self._create(request, u"services")

        @app.route(u"/namespaces/<namespace>/services/<service>", methods=[u"PUT"])
        def replace_service(self, request, namespace, service):
            """
            Replace an existing Service.
            """
            return self._replace(
                request,
                u"services",
                namespace,
                service,
            )

        @app.route(u"/services", methods=[u"GET"])
        def list_services(self, request):
            """
            Get all existing Services.
            """
            return self._list(request, None, u"services")

        @app.route(u"/namespaces/<namespace>/services/<service>", methods=[u"GET"])
        def get_service(self, request, namespace, service):
            """
            Get one Service by name.
            """
            return self._get(
                request,
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
                request, u"services", namespace, service,
            )

    with app.subroute(u"/apis/extensions/v1beta1") as app:
        @app.route(u"/namespaces/<namespace>/deployments", methods=[u"POST"])
        def create_deployment(self, request, namespace):
            """
            Create a new Deployment.
            """
            return self._create(
                request,
                u"deployments",
            )

        @app.route(u"/namespaces/<namespace>/deployments/<deployment>", methods=[u"PUT"])
        def replace_deployment(self, request, namespace, deployment):
            """
            Replace an existing Deployment.
            """
            return self._replace(
                request,
                u"deployments",
                namespace,
                deployment,
            )

        @app.route(u"/deployments", methods=[u"GET"])
        def list_deployments(self, request):
            """
            Get all existing Deployments.
            """
            return self._list(request, None, u"deployments")

        @app.route(u"/namespaces/<namespace>/deployments/<deployment>", methods=[u"GET"])
        def get_deployment(self, request, namespace, deployment):
            """
            Get one Deployment by name.
            """
            return self._get(
                request,
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
                request, u"deployments", namespace, deployment,
            )

        @app.route(u"/namespaces/<namespace>/replicasets", methods=[u"POST"])
        def create_replicaset(self, request, namespace):
            """
            Create a new ReplicaSet.
            """
            return self._create(
                request,
                u"replicasets",
            )

        @app.route(u"/namespaces/<namespace>/replicasets/<replicaset>", methods=[u"PUT"])
        def replace_replicaset(self, request, namespace, replicaset):
            """
            Replace an existing ReplicaSet.
            """
            return self._replace(
                request,
                u"replicasets",
                namespace,
                replicaset,
            )

        @app.route(u"/replicasets", methods=[u"GET"])
        def list_replicasets(self, request):
            """
            Get all existing ReplicaSets.
            """
            return self._list(request, None, u"replicasets")

        @app.route(u"/namespaces/<namespace>/replicasets/<replicaset>", methods=[u"GET"])
        def get_replicaset(self, request, namespace, replicaset):
            """
            Get one ReplicaSet by name.
            """
            return self._get(
                request,
                u"replicasets",
                namespace,
                replicaset,
            )

        @app.route(u"/namespaces/<namespace>/replicasets/<replicaset>", methods=[u"DELETE"])
        def delete_replicaset(self, request, namespace, replicaset):
            """
            Delete one ReplicaSet by name.
            """
            return self._delete(
                request, u"replicasets", namespace, replicaset,
            )
