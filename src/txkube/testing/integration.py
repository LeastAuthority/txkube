# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Integration test generator for ``txkube.IKubernetesClient``.
"""

from re import search
from operator import attrgetter, setitem
from functools import partial, wraps
from itertools import repeat

from zope.interface.verify import verifyObject

from eliot import Message, start_action
from eliot.twisted import DeferredContext

from testtools.matchers import (
    AnyMatch, MatchesAll, MatchesStructure, Is, IsInstance, Equals, Not,
    Contains, AfterPreprocessing, MatchesPredicate, Always,
)

from twisted.python.failure import Failure
from twisted.internet.defer import gatherResults
from twisted.internet.task import deferLater, cooperate
from twisted.web.http import NOT_FOUND, CONFLICT

from .._network import version_to_segments

from ..testing.matchers import MappingEquals, KubernetesObjectDeleted
from ..testing import TestCase, AsynchronousDeferredRunTest

from .. import (
    KubernetesError,
    IKubernetesClient,
)

from .strategies import (
    labels, creatable_namespaces, configmaps,
    deployments, replicasets, pods, services,
)



def async_test_runner():
    # This is a pretty long timeout but it includes sitting around waiting
    # for Kubernetes to finish deleting things so we get better test
    # isolation...  Namespace deletion, specifically, can be slow, with
    # some attempts taking 5 minutes or more.
    return AsynchronousDeferredRunTest.make_factory(timeout=600)



def matches_metadata(expected):
    return MatchesStructure(
        metadata=MatchesStructure(
            namespace=Equals(expected.namespace),
            name=Equals(expected.name),
            # TODO: It would be nice to compare labels but currently that
            # results in an annoying failure because of the confusion of
            # representation of the empty value - {} vs None.
            # https://github.com/LeastAuthority/txkube/issues/66
            # labels=Equals(expected.labels),
        ),
    )


def matches_namespace(ns):
    return matches_metadata(ns.metadata)


def matches_configmap(configmap):
    return matches_metadata(configmap.metadata)


def matches_deployment(deployment):
    return MatchesAll(
        matches_metadata(deployment.metadata),
        # Augh.  I think some kind of "expected is None or values match"
        # matcher would help?
        MatchesStructure(
            spec=MatchesStructure(
                selector=Equals(deployment.spec.selector),
                template=matches_metadata(deployment.spec.template.metadata),
            ),
        ),
    )


def matches_replicaset(replicaset):
    return MatchesAll(
        matches_metadata(replicaset.metadata),
    )


def matches_pod(pod):
    return MatchesAll(
        matches_metadata(pod.metadata),
    )


def matches_service(service):
    return matches_metadata(service.metadata)


def has_uid():
    return MatchesStructure(
        metadata=MatchesStructure(
            uid=Not(Equals(None)),
        ),
    )


def is_active():
    return MatchesStructure(
        status=MatchesStructure(
            phase=Equals(u"Active"),
        ),
    )


def different_name(name):
    if len(name) > 1:
        return name[:-1]
    return name + u"x"



def _named(model, kind, name, namespace=None):
    return kind(metadata=model.v1.ObjectMeta(name=name, namespace=namespace))



def poll(reactor, action, f, intervals):
    """
    Repeatedly call a function.

    :param IReactorTime reactor: The reactor to use for scheduling.

    :param action: An Eliot action in the context of which to call ``f``.

    :param f: A no-argument callable which returns a ``Deferred``.

    :param interfaces: An iterable of numbers giving the delay to use between
        each call to ``f``.  This also limits the total number of calls.  When
        the iterable is exhausted, ``poll`` will stop calling ``f``.

    :return: A ``Deferred`` that fires with any errors encountered by ``f`` or
        with ``StopIteration`` if the end of ``intervals`` is reached.
    """
    intervals = iter(intervals)
    def g():
        with action.context():
            Message.log(poll_iteration=None)
            # Not bothering with DeferredContext here because when
            # deferLater calls g, it can restore the action context from
            # the closure (as it just did a couple lines above).
            d = f()
            d.addCallback(
                lambda ignored: deferLater(reactor, next(intervals), g),
            )
            return d
    d = g()
    d.addCallback(lambda ignored: g())
    return d


_TRY_AGAIN = (
    u"the object has been modified; "
    u"please apply your changes to the latest version and try again"
)

def _replace(client, obj, transformation, retries):
    """
    Try to replace the given object with one that differs by the given
    transformation.

    Try again if the server reports the object has changed.
    """
    d = client.replace(obj.transform(*transformation))
    def maybe_outdated(reason):
        reason.trap(KubernetesError)
        # Uugghh...  This seems to be the only way to identify the condition.
        if _TRY_AGAIN in reason.value.status.message:
            d = client.get(obj)
            d.addCallback(lambda latest: _replace(
                client, latest, transformation, retries - 1
            ))
            return d
        return reason
    if retries > 0:
        d.addErrback(maybe_outdated)
    return d



def does_not_exist(client, obj):
    """
    Wait for ``obj`` to not exist.

    :param IKubernetesClient client: The client to use to determine existence.

    :param IObject obj: The object the existence of which to check.

    :return: A ``Deferred`` that fires when the object does not exist.
    """
    action = start_action(
        action_type=u"poll:start",
        obj=client.model.iobject_to_raw(obj),
    )
    with action.context():
        from twisted.internet import reactor
        d = poll(reactor, action, lambda: client.get(obj), repeat(0.5, 100))
        d = DeferredContext(d)
        # Once we get a NOT FOUND error, we're done.
        def trap_not_found(reason):
            reason.trap(KubernetesError)
            if reason.value.code == NOT_FOUND:
                return None
            return reason
        d.addErrback(trap_not_found)
        def trap_stop_iteration(reason):
            reason.trap(StopIteration)
            Message.log(
                does_not_exist=u"timeout",
                obj=client.model.iobject_to_raw(obj),
            )
            return None
        d.addErrback(trap_stop_iteration)
        return d.addActionFinish()


def needs(**to_create):
    """
    Create a function decorator which will create certain Kubernetes objects
    before calling the decorated function and delete them after it completes.

    This requires the decorated functions accept a first argument with a
    ``client`` attribute bound to an ``IKubernetesClient``.

    :param to_create: Keyword arguments with values of Hypothesis strategies
        which build ``IObject`` providers.  After being created, these objects
        will be passed to the decorated function using the same keyword
        arguments.

    :return: A function decorator.
    """
    def build_objects():
        objs = {}
        names = set()
        for name, strategy in to_create.iteritems():
            while True:
                obj = strategy.example()
                if obj.metadata.name not in names:
                    names.add(obj.metadata.name)
                    break
            objs[name] = obj
        return objs
    return _needs_objects(build_objects)



def _needs_objects(get_objects):
    def no_grace(model):
        return model.v1.DeleteOptions(gracePeriodSeconds=0)

    def decorator(f):
        @wraps(f)
        def wrapper(self, *a, **kw):
            # Get the objects we're supposed to create.
            to_create = get_objects()

            # Check to make sure there aren't keyword argument conflicts.  I
            # doubt this is an exhaustive safety check.
            overlap = set(to_create) & set(kw)
            if overlap:
                raise TypeError(
                    "Conflict between @needs() and **kw: {}".format(overlap)
                )

            def cleanup(obj):
                # Delete an object, if it exists, and wait for it to stop
                # existing.
                d = self.client.delete(obj, no_grace(self.model))
                # Some Kubernetes objects take a while to be deleted.
                # Specifically, Namespaces go though a slow "Terminating"
                # phase where things they contain are cleaned up.  Delay
                # cleanup completion until objects are *really* gone.
                d.addBoth(lambda ignored: does_not_exist(self.client, obj))
                return d

            def create(obj):
                # Create some object and arrange for it to be deleted later.
                d = self.client.create(obj)
                def created(result):
                    self.addCleanup(lambda: cleanup(result))
                    return result
                d.addCallback(created)
                return d

            # Keep track of the objects we created - keyed on name.
            created = {}

            # Create an object, deleting an existing one that's in the way
            # first, if necessary.
            def ensure(obj):
                d = cleanup(obj)
                d.addCallback(lambda ignored: create(obj))
                return d

            # Create the objects.
            task = cooperate(
                ensure(obj).addCallback(partial(setitem, created, name))
                for (name, obj)
                in sorted(to_create.items())
            )
            d = task.whenDone()

            # Call the decorated function.
            d.addCallback(lambda ignored: kw.update(created))
            d.addCallback(lambda ignored: f(self, *a, **kw))
            return d
        return wrapper
    return decorator



class _VersionTestsMixin(object):
    def test_version(self):
        """
        The server version can be retrieved using ``IKubernetesClient.version``.
        """
        d = self.client.version()
        d.addCallback(
            lambda version: self.assertThat(
                version, MatchesStructure(
                    major=IsInstance(unicode),
                    minor=IsInstance(unicode),
                ),
            ),
        )
        return d



class _NamespaceTestsMixin(object):
    @needs(obj=creatable_namespaces())
    def test_namespace(self, obj):
        """
        ``Namespace`` objects can be created and retrieved using the ``create``
        and ``list`` methods of ``IKubernetesClient``.
        """
        d = self.client.list(self.model.v1.Namespace)
        def check_namespaces(namespaces):
            self.assertThat(namespaces, IsInstance(self.model.v1.NamespaceList))
            # There are some built-in namespaces that we'll ignore.  If we
            # find the one we created, that's sufficient.
            self.assertThat(
                namespaces.items,
                AnyMatch(MatchesAll(matches_namespace(obj), has_uid(), is_active())),
            )
        d.addCallback(check_namespaces)
        return d


    @needs(obj=creatable_namespaces())
    def test_namespace_retrieval(self, obj):
        """
        A specific ``Namespace`` object can be retrieved by name using
        ``IKubernetesClient.get``.
        """
        return self._global_object_retrieval_by_name_test(
            obj,
            self.model.v1.Namespace,
            matches_namespace,
        )


    def test_namespace_replacement(self):
        """
        A specific ``Namespace`` object can be replaced by name using
        ``IKubernetesClient.replace``.
        """
        return self._object_replacement_test(
            None,
            creatable_namespaces(self.model),
            matches_namespace,
        )


    @needs(obj=creatable_namespaces())
    def test_namespace_deletion(self, obj):
        """
        ``IKubernetesClient.delete`` can be used to delete ``Namespace``
        objects.
        """
        d = self.client.delete(obj)
        def deleted_namespace(ignored):
            return self.client.list(self.model.v1.Namespace)
        d.addCallback(deleted_namespace)
        def check_namespaces(collection):
            active = list(
                ns.metadata.name
                for ns
                in collection.items
                if ns.status.phase == u"Active"
            )
            self.assertThat(
                active,
                Not(Contains(obj.metadata.name)),
            )
        d.addCallback(check_namespaces)
        return d


    def test_duplicate_namespace_rejected(self):
        """
        ``IKubernetesClient.create`` returns a ``Deferred`` that fails with
        ``KubernetesError`` if it is called with a ``Namespace`` object
        with the same name as a *Namespace* which already exists.
        """
        return self._create_duplicate_rejected_test(
            None,
            strategy=creatable_namespaces(self.model),
        )



class _ConfigMapTestsMixin(object):
    @needs(namespace=creatable_namespaces())
    def test_duplicate_configmap_rejected(self, namespace):
        """
        ``IKubernetesClient.create`` returns a ``Deferred`` that fails with
        ``KubernetesError`` if it is called with a ``ConfigMap`` object
        with the same name as a *ConfigMap* which already exists in the
        same namespace.
        """
        return self._create_duplicate_rejected_test(
            namespace,
            strategy=configmaps(self.model),
        )


    @needs(namespace=creatable_namespaces())
    def test_configmap(self, namespace):
        """
        ``ConfigMap`` objects can be created and retrieved using the ``create``
        and ``list`` methods of ``IKubernetesClient``.
        """
        self._create_list_test(
            namespace, configmaps(self.model), self.model.v1.ConfigMap,
            self.model.v1.ConfigMapList,
            matches_configmap,
        )


    def test_configmap_retrieval(self):
        """
        A specific ``ConfigMap`` object can be retrieved by name using
        ``IKubernetesClient.get``.
        """
        return self._namespaced_object_retrieval_by_name_test(
            configmaps(self.model),
            self.model.v1.ConfigMap,
            matches_configmap,
        )


    @needs(namespace=creatable_namespaces())
    def test_configmap_replacement(self, namespace):
        """
        A specific ``ConfigMap`` object can be replaced by name using
        ``IKubernetesClient.replace``.
        """
        return self._object_replacement_test(
            namespace,
            configmaps(self.model),
            matches_configmap,
        )


    def test_configmap_deletion(self):
        """
        A specific ``ConfigMap`` object can be deleted by name using
        ``IKubernetesClient.delete``.
        """
        return self._namespaced_object_deletion_by_name_test(
            configmaps(self.model),
            self.model.v1.ConfigMap,
        )


    ns_strategy = creatable_namespaces()
    @needs(ns_a=ns_strategy, ns_b=ns_strategy)
    def test_configmaps_sorted(self, ns_a, ns_b):
        """
        ``ConfigMap`` objects retrieved with ``IKubernetesClient.list`` appear in
        sorted order, with (namespace, name) as the sort key.
        """
        strategy = configmaps(self.model)
        objs = [
            strategy.example().transform(
                [u"metadata", u"namespace"], ns_a.metadata.name,
            ),
            strategy.example().transform(
                [u"metadata", u"namespace"], ns_b.metadata.name,
            ),
        ]
        d = gatherResults(list(self.client.create(obj) for obj in objs))
        def created_configmaps(ignored):
            return self.client.list(self.model.v1.ConfigMap)
        d.addCallback(created_configmaps)
        def check_configmaps(collection):
            self.expectThat(collection, items_are_sorted())
        d.addCallback(check_configmaps)
        return d



class _ReplicaSetTestsMixin(object):
    @needs(namespace=creatable_namespaces())
    def test_replicaset(self, namespace):
        """
        ``ReplicaSet`` objects can be created and retrieved using the ``create``
        and ``list`` methods of ``IKubernetesClient``.
        """
        return self._create_list_test(
            namespace, replicasets(self.model), self.model.v1beta1.ReplicaSet,
            self.model.v1beta1.ReplicaSetList, matches_replicaset,
        )


    @needs(namespace=creatable_namespaces())
    def test_duplicate_replicaset_rejected(self, namespace):
        """
        ``IKubernetesClient.create`` returns a ``Deferred`` that fails with
        ``KubernetesError`` if it is called with a ``ReplicaSet`` object with
        the same name as a *ReplicaSet* which already exists in the same
        namespace.
        """
        return self._create_duplicate_rejected_test(
            namespace,
            strategy=replicasets(self.model),
        )


    def test_replicaset_retrieval(self):
        """
        A specific ``ReplicaSet`` object can be retrieved by name using
        ``IKubernetesClient.get``.
        """
        return self._namespaced_object_retrieval_by_name_test(
            replicasets(self.model),
            self.model.v1beta1.ReplicaSet,
            matches_replicaset,
        )


    @needs(namespace=creatable_namespaces())
    def test_replicaset_replacement(self, namespace):
        """
        A specific ``ReplicaSet`` object can be replaced by name using
        ``IKubernetesClient.replace``.
        """
        return self._object_replacement_test(
            namespace,
            replicasets(self.model),
            matches_replicaset,
        )


    def test_replicaset_deletion(self):
        """
        A specific ``ReplicaSet`` object can be deleted by name using
        ``IKubernetesClient.delete``.
        """
        return self._namespaced_object_deletion_by_name_test(
            replicasets(self.model),
            self.model.v1beta1.ReplicaSet,
        )



class _PodTestsMixin(object):
    @needs(namespace=creatable_namespaces())
    def test_pod(self, namespace):
        """
        ``Pod`` objects can be created and retrieved using the ``create`` and
        ``list`` methods of ``IKubernetesClient``.
        """
        return self._create_list_test(
            namespace, pods(self.model), self.model.v1.Pod,
            self.model.v1.PodList, matches_pod,
        )


    @needs(namespace=creatable_namespaces())
    def test_duplicate_pod_rejected(self, namespace):
        """
        ``IKubernetesClient.create`` returns a ``Deferred`` that fails with
        ``KubernetesError`` if it is called with a ``Pod`` object with the
        same name as a *Pod* which already exists in the same namespace.
        """
        return self._create_duplicate_rejected_test(
            namespace,
            strategy=pods(self.model),
        )


    def test_pod_retrieval(self):
        """
        A specific ``Pod`` object can be retrieved by name using
        ``IKubernetesClient.get``.
        """
        return self._namespaced_object_retrieval_by_name_test(
            pods(self.model),
            self.model.v1.Pod,
            matches_pod,
        )


    @needs(namespace=creatable_namespaces())
    def test_pod_replacement(self, namespace):
        """
        A specific ``Pod`` object can be replaced by name using
        ``IKubernetesClient.replace``.
        """
        return self._object_replacement_test(
            namespace,
            pods(self.model),
            matches_pod,
        )


    def test_pod_deletion(self):
        """
        A specific ``Pod`` object can be deleted by name using
        ``IKubernetesClient.delete``.
        """
        return self._namespaced_object_deletion_by_name_test(
            pods(self.model),
            self.model.v1.Pod,
        )



class _DeploymentTestsMixin(object):
    @needs(namespace=creatable_namespaces())
    def test_deployment(self, namespace):
        """
        ``Deployment`` objects can be created and retrieved using the ``create``
        and ``list`` methods of ``IKubernetesClient``.
        """
        return self._create_list_test(
            namespace, deployments(self.model), self.model.v1beta1.Deployment,
            self.model.v1beta1.DeploymentList, matches_deployment,
        )


    @needs(namespace=creatable_namespaces())
    def test_duplicate_deployment_rejected(self, namespace):
        """
        ``IKubernetesClient.create`` returns a ``Deferred`` that fails with
        ``KubernetesError`` if it is called with a ``Deployment`` object with
        the same name as a *Deployment* which already exists in the same
        namespace.
        """
        return self._create_duplicate_rejected_test(
            namespace,
            strategy=deployments(self.model),
        )


    def test_deployment_retrieval(self):
        """
        A specific ``Deployment`` object can be retrieved by name using
        ``IKubernetesClient.get``.
        """
        return self._namespaced_object_retrieval_by_name_test(
            deployments(self.model),
            self.model.v1beta1.Deployment,
            matches_deployment,
        )


    @needs(namespace=creatable_namespaces())
    def test_deployment_replacement(self, namespace):
        """
        A specific ``Deployment`` object can be replaced by name using
        ``IKubernetesClient.replace``.
        """
        return self._object_replacement_test(
            namespace,
            deployments(self.model),
            matches_deployment,
        )


    def test_deployment_deletion(self):
        """
        A specific ``Deployment`` object can be deleted by name using
        ``IKubernetesClient.delete``.
        """
        return self._namespaced_object_deletion_by_name_test(
            deployments(self.model),
            self.model.v1beta1.Deployment,
        )



class _ServiceTestsMixin(object):
    @needs(namespace=creatable_namespaces())
    def test_service(self, namespace):
        """
        ``Service`` objects can be created and retrieved using the ``create`` and
        ``list`` methods of ``IKubernetesClient``.
        """
        self._create_list_test(
            namespace, services(self.model), self.model.v1.Service,
            self.model.v1.ServiceList,
            matches_service,
        )


    @needs(namespace=creatable_namespaces())
    def test_duplicate_service_rejected(self, namespace):
        """
        ``IKubernetesClient.create`` returns a ``Deferred`` that fails with
        ``KubernetesError`` if it is called with a ``ConfigMap`` object
        with the same name as a *ConfigMap* which already exists in the
        same namespace.
        """
        return self._create_duplicate_rejected_test(
            namespace,
            strategy=configmaps(self.model),
        )


    def test_service_retrieval(self):
        """
        A specific ``Service`` object can be retrieved by name using
        ``IKubernetesClient.get``.
        """
        return self._namespaced_object_retrieval_by_name_test(
            services(self.model),
            self.model.v1.Service,
            matches_service,
        )


    @needs(namespace=creatable_namespaces())
    def test_service_replacement(self, namespace):
        """
        A specific ``Service`` object can be replaced by name using
        ``IKubernetesClient.replace``.
        """
        return self._object_replacement_test(
            namespace,
            services(self.model),
            matches_service,
        )


    def test_service_deletion(self):
        """
        A specific ``Service`` object can be deleted by name using
        ``IKubernetesClient.delete``.
        """
        return self._namespaced_object_deletion_by_name_test(
            services(self.model),
            self.model.v1.Service,
        )



def kubernetes_client_tests(get_kubernetes):
    class KubernetesClientIntegrationTests(
        _VersionTestsMixin,
        _NamespaceTestsMixin,
        _ConfigMapTestsMixin,
        _DeploymentTestsMixin,
        _ReplicaSetTestsMixin,
        _PodTestsMixin,
        _ServiceTestsMixin,
        TestCase
    ):
        run_tests_with = async_test_runner()

        def setUp(self):
            super(KubernetesClientIntegrationTests, self).setUp()
            self.kubernetes = get_kubernetes(self)
            d = self.kubernetes.versioned_client()
            def got_client(client):
                self.client = client
                self.model = self.client.model
                self.addCleanup(self._cleanup)
            d.addCallback(got_client)
            return d


        def _cleanup(self):
            pool = getattr(self.client.agent, "_pool", None)
            if pool is None:
                return None
            from twisted.internet import reactor
            return gatherResults([
                pool.closeCachedConnections(),
                # Semi-work-around for
                # https://twistedmatrix.com/trac/ticket/8998
                deferLater(reactor, 1.0, lambda: None),
            ])


        def test_interfaces(self):
            """
            The client provides ``txkube.IKubernetesClient``.
            """
            verifyObject(IKubernetesClient, self.client)


        def test_not_found(self):
            """
            ``IKubernetesClient.list`` returns a ``Deferred`` that fails with
            ``KubernetesError`` when the server responds with an HTTP NOT
            FOUND status.
            """
            # Invent a type that the server isn't going to recognize.  This
            # could happen if we're talking to a server that is missing some
            # extension we thought it had, for example.
            class Mythical(object):
                apiVersion = u"v6txkube2"
                kind = u"Mythical"
                metadata = self.model.v1.ObjectMeta()

            # The client won't know where to route the request without this.
            # There is a more general problem here that the model is missing
            # some unpredictable information about where the relevant APIs are
            # exposed in the URL hierarchy.
            version_to_segments[Mythical.apiVersion] = (
                u"apis", u"extensions", Mythical.apiVersion,
            )
            self.addCleanup(lambda: version_to_segments.pop(Mythical.apiVersion))

            d = self.client.list(Mythical)
            def failed(reason):
                self.assertThat(reason, IsInstance(Failure))
                reason.trap(KubernetesError)
                self.assertThat(
                    reason.value,
                    MatchesStructure(
                        code=Equals(NOT_FOUND),
                        status=Equals(self.model.v1.Status(
                            metadata={},
                            status=u"Failure",
                            message=u"the server could not find the requested resource",
                            reason=u"NotFound",
                            details=dict(),
                            code=NOT_FOUND,
                        )),
                    ),
                )
            d.addBoth(failed)
            return d


        def _global_object_retrieval_by_name_test(self, obj, kind, matches):
            """
            Verify that a particular kind of non-namespaced Kubernetes object (such as
            *Namespace* or *PersistentVolume*) can be retrieved by name by
            calling ``IKubernetesClient.get`` with the ``IObject``
            corresponding to that kind as long as the object has its *name*
            metadata populated.
            """
            d = self.client.get(_named(self.model, kind, name=obj.metadata.name))
            def got_object(retrieved):
                self.assertThat(retrieved, matches(obj))
            d.addCallback(got_object)
            return d


        def _object_replacement_test(self, namespace, strategy, matches):
            """
            Verify that an existing object can be replaced by a new one.

            :param namespace: If the object belongs in a namespace, the name
                of an existing namespace to create it in.  ``None`` if not.

            :param strategy: A Hypothesis strategy for building the object to
                create and the object to replace it with.

            :param matches: A one-argument caller which takes the expected
                object and returns a testtools matcher for it.  Since created
                objects have some unpredictable server-generated fields, this
                matcher can compare just the important, predictable parts of
                the object.

            :return: A ``Deferred`` that fires when the behavior has been
                verified.
            """
            original = strategy.example()
            if namespace is not None:
                original = original.transform(
                    [u"metadata", u"namespace"], namespace.metadata.name,
                )
            # Different kinds of objects have different constraints on what
            # they can be replaced with.  To avoid running into those, make
            # the replacement just like the original but with some different
            # labels.  Hopefully this will always be allowed.
            #
            # Also, make sure _some_ labels are set to avoid triggering extra
            # server processing in some cases.  For example, Deployment
            # inherits labels from its template spec if its own labels are
            # empty.
            replacement_labels = labels().filter(lambda labels: len(labels)).example()

            d = self.client.create(original)
            def created(created):
                # Use the created object as the basis for the replacement
                # object.  Various server-populated fields (varying between
                # different kinds of objects) must match in the replacement.
                # Using our original object as the starting point will mess
                # these.
                transformation = (
                    [u"metadata", u"labels"],
                    replacement_labels,
                )
                return _replace(self.client, created, transformation, retries=2)
            d.addCallback(created)
            def replaced(result):
                self.expectThat(
                    result.metadata.labels,
                    MappingEquals(replacement_labels),
                )
                return self.client.get(original)
            d.addCallback(replaced)
            def retrieved(result):
                self.expectThat(
                    result.metadata.labels,
                    MappingEquals(replacement_labels),
                )
            d.addCallback(retrieved)
            return d


        def _create_list_test(self, namespace, strategy, cls, list_cls, matches):
            """
            Verify that a particular kind of namespaced Kubernetes object (such as
            *Service* or *Secret*) can be created using
            ``IKubernetesClient.create`` and then appears in the result of
            ``IKubernetesClient.list``.
            """
            # Get an object in the namespace.
            expected = strategy.example().transform(
                [u"metadata", u"namespace"],
                namespace.metadata.name,
            )
            d = self.client.create(expected)
            def created(actual):
                self.assertThat(actual, matches(expected))
                return self.client.list(cls)
            d.addCallback(created)
            def check(collection):
                self.assertThat(collection, IsInstance(list_cls))
                self.assertThat(collection.items, AnyMatch(matches(expected)))
            d.addCallback(check)
            return d


        def _create_duplicate_rejected_test(self, namespace, strategy):
            """
            Verify an object cannot be created if its name (and maybe namespace) is
            already taken.

            :param IObject obj: Some object to create and try to create again.

            :param unicode kind: The name of the collection of the *kind* of
                ``obj``, lowercase.  For example, *configmaps*.
            """
            obj = strategy.example()
            group = _infer_api_group(obj.apiVersion)

            # Put it in the namespace.
            if namespace is not None:
                obj = obj.transform(
                    [u"metadata", u"namespace"],
                    namespace.metadata.name,
                )
            d = self.client.create(obj)
            def created(ignored):
                return self.client.create(obj)
            d.addCallback(created)
            def failed(reason):
                self.assertThat(reason, IsInstance(Failure))
                reason.trap(KubernetesError)
                self.assertThat(
                    reason.value,
                    MatchesStructure(
                        code=Equals(CONFLICT),
                        status=MatchesStructure(
                            metadata=Equals(self.model.v1.ListMeta()),
                            status=Equals(u"Failure"),
                            # Error text is wonky and changes from version to
                            # version.  It's not a reliable source of
                            # information so don't bother making any
                            # particular assertions about its contents.
                            message=Always(),
                            reason=Equals(u"AlreadyExists"),
                            details=MatchesStructure.byEquality(
                                name=obj.metadata.name,
                                kind=obj.kind.lower() + u"s",
                                group=group,
                            ),
                            code=Equals(CONFLICT),
                        ),
                    ),
                )
            d.addBoth(failed)
            return d


        ns_strategy = creatable_namespaces()
        @needs(
            victim_namespace=ns_strategy,
            bystander_namespace=ns_strategy,
        )
        def _namespaced_object_deletion_by_name_test(
            self, strategy, cls, victim_namespace, bystander_namespace
        ):
            """
            Verify that a particular kind of namespaced Kubernetes object (such as
            *Deployment* or *Service*) can be deleted by name by calling
            ``IKubernetesClient.delete`` with the ``IObject`` corresponding to
            that kind as long as the object has its *name* and *namespace*
            metadata populated.

            :param strategy: A Hypothesis strategy for building the namespaced
                object to create and then retrieve.

            :param cls: The ``IObject`` implementation corresponding to the
                objects ``strategy`` can build.

            :param v1.Namespace victim_namespace: An existing namespace into
                which the probe object can be created (not part of the
                interface; value supplied by the decorator).

            :param v1.Namespace bystander_namespace: An existing namespace
                into which another object can be created (not part of the
                interface; value supplied by the decorator).

            :return: A ``Deferred`` that fires when the behavior has been
                verified.
            """
            # This object will be the target of the deletion.
            victim = strategy.example()
            # These bystanders should be left alone.
            bystander_a = strategy.example()
            bystander_b = strategy.example()
            victim = victim.transform(
                # Put the victim in the victim namespace.
                [u"metadata", u"namespace"], victim_namespace.metadata.name,
            )
            bystander_a = bystander_a.transform(
                # Put a bystander in the victim namespace, too.
                [u"metadata", u"namespace"], victim_namespace.metadata.name,
                # Also, be completely certain the bystander has a different
                # name.
                [u"metadata", u"name"], different_name(victim.metadata.name),
            )
            bystander_b = bystander_b.transform(
                # Put a bystander in another namespace too.
                [u"metadata", u"namespace"], bystander_namespace.metadata.name,
            )
            d = gatherResults(list(
                self.client.create(o)
                for o
                in [victim, bystander_a, bystander_b]
            ))
            def created_object(ignored):
                return self.client.delete(
                    _named(
                        self.model,
                        cls,
                        namespace=victim.metadata.namespace, name=victim.metadata.name,
                    ),
                    self.model.v1.DeleteOptions(gracePeriodSeconds=0),
                )
            d.addCallback(created_object)
            def deleted_object(result):
                self.expectThat(result, Is(None))
                return self.client.list(cls)
            d.addCallback(deleted_object)
            def listed_objects(collection):
                self.expectThat(
                    collection,
                    MatchesAll(
                        Not(KubernetesObjectDeleted(bystander_a)),
                        Not(KubernetesObjectDeleted(bystander_b)),
                        KubernetesObjectDeleted(victim),
                    ),
                )
            d.addCallback(listed_objects)
            return d


        @needs(namespace=creatable_namespaces())
        def _namespaced_object_retrieval_by_name_test(self, strategy, cls, matches, namespace):
            """
            Verify that a particular kind of namespaced Kubernetes object (such as
            *ConfigMap* or *PersistentVolumeClaim*) can be retrieved by name
            by calling ``IKubernetesClient.get`` with the ``IObject``
            corresponding to that kind as long as the object has its *name*
            and *namespace* metadata populated.

            :param strategy: A Hypothesis strategy for building the namespaced
                object to create and then retrieve.

            :param cls: The ``IObject`` implementation corresponding to the
                objects ``strategy`` can build.

            :param matches: A one-argument caller which takes the expected
                object and returns a testtools matcher for it.  Since created
                objects have some unpredictable server-generated fields, this
                matcher can compare just the important, predictable parts of
                the object.

            :param v1.Namespace namespace: An existing namespace into which
                the probe object can be created.

            :return: A ``Deferred`` that fires when the behavior has been
                verified.
            """
            obj = strategy.example()
            group = _infer_api_group(obj.apiVersion)
            # Move it to the namespace for this test.
            obj = obj.transform([u"metadata", u"namespace"], namespace.metadata.name)
            d = self.client.create(obj)
            def created_object(created):
                return self.client.get(_named(
                    self.model,
                    cls,
                    namespace=obj.metadata.namespace, name=obj.metadata.name,
                ))
            d.addCallback(created_object)
            def got_object(retrieved):
                self.expectThat(retrieved, matches(obj))
                # Try retrieving an object with the same name but a different
                # namespace.  We shouldn't find it.
                #
                # First, compute a legal but non-existing namespace name.
                bogus_namespace = different_name(obj.metadata.namespace)
                return self.client.get(
                    _named(
                        self.model,
                        cls,
                        namespace=bogus_namespace,
                        name=obj.metadata.name,
                    ),
                )
            d.addCallback(got_object)
            def check_error(reason):
                self.assertThat(reason, IsInstance(Failure))
                reason.trap(KubernetesError)
                self.assertThat(
                    reason.value,
                    MatchesStructure(
                        code=Equals(NOT_FOUND),
                        status=MatchesStructure(
                            metadata=Equals(self.model.v1.ListMeta()),
                            status=Equals(u"Failure"),
                            # Error text is wonky and changes from version to
                            # version.  It's not a reliable source of
                            # information so don't bother making any
                            # particular assertions about its contents.
                            message=Always(),
                            reason=Equals(u"NotFound"),
                            details=MatchesStructure.byEquality(
                                kind=obj.kind.lower() + u"s",
                                name=obj.metadata.name,
                                group=group,
                            ),
                            code=Equals(NOT_FOUND),
                        ),
                    ),
                )
            d.addBoth(check_error)
            return d

    return KubernetesClientIntegrationTests



def items_are_sorted():
    """
    Match an ObjectCollection if its items can be iterated in the Kubernetes
    canonical sort order - lexicographical by namespace, name.
    """
    def key(obj):
        return (
            getattr(obj.metadata, "namespace", None),
            obj.metadata.name,
        )

    def is_sorted(items, key):
        return list(items) == sorted(items, key=key)

    return AfterPreprocessing(
        attrgetter("items"),
        MatchesPredicate(
            partial(is_sorted, key=key),
            u"%s is not sorted by namespace, name",
        ),
    )



_CORE_PATTERNS = [
    # 1.6, 1.7
    u"^io.k8s.kubernetes.pkg.api.",
    u"^io.k8s.apimachinery.pkg.apis.meta.",

    # 1.5
    u"^v1$",
]



def _infer_api_group(apiVersion):
    for pattern in _CORE_PATTERNS:
        if search(pattern, apiVersion) is not None:
            return None
    return u"extensions"
