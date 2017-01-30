# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Integration test generator for ``txkube.IKubernetesClient``.
"""

from operator import attrgetter, setitem
from functools import partial, wraps

from zope.interface.verify import verifyObject

from testtools.matchers import (
    AnyMatch, MatchesAll, MatchesStructure, IsInstance, Equals, Not, Contains,
    AfterPreprocessing, MatchesPredicate,
)

from testtools.twistedsupport import AsynchronousDeferredRunTest
from testtools import run_test_with

from twisted.python.failure import Failure
from twisted.internet.defer import gatherResults
from twisted.internet.task import deferLater, cooperate
from twisted.web.http import NOT_FOUND, CONFLICT

from ..testing import TestCase

from .. import (
    KubernetesError,
    IKubernetesClient, NamespaceStatus, Namespace, ConfigMap, ObjectCollection,
    v1,
)

from .strategies import creatable_namespaces, configmaps


def async(f):
    def _async(*a, **kw):
        kw["timeout"] = 5.0
        return AsynchronousDeferredRunTest(*a, **kw)
    return run_test_with(_async)(f)



def matches_namespace(ns):
    return MatchesStructure(
        metadata=MatchesStructure(
            name=Equals(ns.metadata.name),
        ),
    )



def matches_configmap(configmap):
    return MatchesStructure(
        metadata=MatchesStructure(
            namespace=Equals(configmap.metadata.namespace),
            name=Equals(configmap.metadata.name),
        ),
    )


def has_uid():
    return MatchesStructure(
        metadata=MatchesStructure(
            uid=Not(Equals(None)),
        ),
    )


def is_active():
    return MatchesStructure(
        status=Equals(NamespaceStatus.active()),
    )


def kubernetes_client_tests(get_kubernetes):
    class KubernetesClientIntegrationTests(TestCase):
        def setUp(self):
            super(KubernetesClientIntegrationTests, self).setUp()
            self.kubernetes = get_kubernetes(self)
            self.client = self.kubernetes.client()
            self.addCleanup(self._cleanup)

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


        @async
        def test_namespace(self):
            """
            ``Namespace`` objects can be created and retrieved using the ``create``
            and ``list`` methods of ``IKubernetesClient``.
            """
            obj = creatable_namespaces().example()
            d = self.client.create(obj)
            def created_namespace(created):
                self.assertThat(created, matches_namespace(obj))
                return self.client.list(Namespace)
            d.addCallback(created_namespace)
            def check_namespaces(namespaces):
                self.assertThat(namespaces, IsInstance(ObjectCollection))
                # There are some built-in namespaces that we'll ignore.  If we
                # find the one we created, that's sufficient.
                self.assertThat(
                    namespaces.items,
                    AnyMatch(MatchesAll(matches_namespace(obj), has_uid(), is_active())),
                )
            d.addCallback(check_namespaces)
            return d


        def _global_object_retrieval_by_name_test(self, strategy, kind, matches):
            """
            Verify that a particular kind of non-namespaced Kubernetes object (such as
            *Namespace* or *PersistentVolume*) can be retrieved by name by
            calling ``IKubernetesClient.get`` with the ``IObject``
            corresponding to that kind as long as the object has its *name*
            metadata populated.
            """
            obj = strategy.example()
            d = self.client.create(obj)
            def created_object(created):
                return self.client.get(kind.named(obj.metadata.name))
            d.addCallback(created_object)
            def got_object(retrieved):
                self.assertThat(retrieved, matches(obj))
            d.addCallback(got_object)
            return d


        @async
        def test_duplicate_namespace_rejected(self):
            """
            ``IKubernetesClient.create`` returns a ``Deferred`` that fails with
            ``KubernetesClient`` if it is called with a ``Namespace`` object
            with the same name as a *Namespace* which already exists.
            """
            obj = creatable_namespaces().example()
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
                        status=Equals(v1.Status(
                            metadata={},
                            status=u"Failure",
                            message=u"namespaces \"{}\" already exists".format(obj.metadata.name),
                            reason=u"AlreadyExists",
                            details=dict(
                                name=obj.metadata.name,
                                kind=u"namespaces",
                            ),
                            code=CONFLICT,
                        )),
                    ),
                )
            d.addBoth(failed)
            return d


        @async
        def test_namespace_retrieval(self):
            """
            A specific ``Namespace`` object can be retrieved by name using
            ``IKubernetesClient.get``.
            """
            return self._global_object_retrieval_by_name_test(
                creatable_namespaces(),
                Namespace,
                matches_namespace,
            )


        @async
        def test_namespace_deletion(self):
            """
            ``IKubernetesClient.delete`` can be used to delete ``Namespace``
            objects.
            """
            obj = creatable_namespaces().example()
            d = self.client.create(obj)
            def created_namespace(created):
                return self.client.delete(created)
            d.addCallback(created_namespace)
            def deleted_namespace(ignored):
                return self.client.list(Namespace)
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


        @async
        def test_configmap(self):
            """
            ``ConfigMap`` objects can be created and retrieved using the ``create``
            and ``list`` methods of ``IKubernetesClient``.
            """
            namespace = creatable_namespaces().example()
            # Move the object into the namespace we're going to create.
            obj = configmaps().example().transform(
                [u"metadata", u"namespace"],
                namespace.metadata.name,
            )
            d = self.client.create(namespace)
            def created_namespace(ignored):
                return self.client.create(obj)
            d.addCallback(created_namespace)
            def created_configmap(created):
                self.assertThat(created, matches_configmap(obj))
                return self.client.list(ConfigMap)
            d.addCallback(created_configmap)
            def check_configmaps(collection):
                self.assertThat(collection, IsInstance(ObjectCollection))
                self.assertThat(collection.items, AnyMatch(matches_configmap(obj)))
            d.addCallback(check_configmaps)
            return d


        @needs(namespace=creatable_namespaces().example())
        def _namespaced_object_retrieval_by_name_test(self, strategy, kind, matches, namespace):
            """
            Verify that a particular kind of namespaced Kubernetes object (such as
            *ConfigMap* or *PersistentVolumeClaim*) can be retrieved by name
            by by calling ``IKubernetesClient.get`` with the ``IObject``
            corresponding to that kind as long as the object has its *name*
            metadata populated.
            """
            obj = strategy.example()
            # Move it to the namespace for this test.
            obj = obj.transform([u"metadata", u"namespace"], namespace.metadata.name)
            d = self.client.create(obj)
            def created_object(created):
                return self.client.get(kind.named(obj.metadata.namespace, obj.metadata.name))
            d.addCallback(created_object)
            def got_object(retrieved):
                self.expectThat(retrieved, matches(obj))
                # Try retrieving an object with the same name but a different
                # namespace.  We shouldn't find it.
                #
                # First, compute a legal but non-existing namespace name.
                bogus_namespace = obj.metadata.namespace
                if len(bogus_namespace) > 1:
                    bogus_namespace = bogus_namespace[:-1]
                else:
                    bogus_namespace += u"x"
                return self.client.get(
                    kind.named(bogus_namespace, obj.metadata.name),
                )
            d.addCallback(got_object)
            def check_error(result):
                self.assertThat(result, IsInstance(Failure))
                result.trap(KubernetesError)
                self.assertThat(result.value.code, Equals(NOT_FOUND))
            d.addBoth(check_error)
            return d


        @async
        def test_configmap_retrieval(self):
            """
            A specific ``ConfigMap`` object can be retrieved by name using
            ``IKubernetesClient.get``.
            """
            return self._namespaced_object_retrieval_by_name_test(
                configmaps(),
                ConfigMap,
                matches_configmap,
            )


        @async
        def test_configmaps_sorted(self):
            """
            ``ConfigMap`` objects retrieved with ``IKubernetesClient.list`` appear in
            sorted order, with (namespace, name) as the sort key.
            """
            strategy = configmaps()
            objs = [strategy.example(), strategy.example()]
            ns = list(
                Namespace(
                    metadata=v1.ObjectMeta(name=obj.metadata.namespace),
                    status=None,
                )
                for obj
                in objs
            )
            d = gatherResults(list(self.client.create(obj) for obj in ns + objs))
            def created_configmaps(ignored):
                return self.client.list(ConfigMap)
            d.addCallback(created_configmaps)
            def check_configmaps(collection):
                self.expectThat(collection, items_are_sorted())
            d.addCallback(check_configmaps)
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


def needs(**to_create):
    """
    Create a function decorator which will create certain Kubernetes objects
    before calling the decorated function and delete them after it completes.

    This requires the decorated functions accept a first argument with a
    ``client`` attribute bound to an ``IKubernetesClient``.

    :param to_create: Keyword arguments with ``IObject`` providers as values.
        After being created, these objects will be passed to the decorated
        function using the same keyword arguments.

    :return: A function decorator.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(self, *a, **kw):
            # Check to make sure there aren't keyword argument conflicts.  I
            # doubt this is an exhaustive safety check.
            overlap = set(to_create) & set(kw)
            if overlap:
                raise TypeError(
                    "Conflict between @needs() and **kw: {}".format(overlap)
                )

            # Create the objects.
            created = {}
            task = cooperate(
                self.client.create(
                    obj
                ).addCallback(
                    partial(setitem, created, name)
                )
                for (name, obj)
                in sorted(to_create.items())
            )
            d = task.whenDone()

            # Call the decorated function.
            d.addCallback(lambda ignored: kw.update(created))
            d.addCallback(lambda ignored: f(self, *a, **kw))

            # Delete the created objects.
            def cleanup(passthrough):
                task = cooperate(
                    self.client.delete(created[name])
                    for name
                    in sorted(to_create, reverse=True)
                    if name in created
                )
                d = task.whenDone()
                d.addCallback(lambda ignored: passthrough)
                return d
            d.addBoth(cleanup)
            return d
        return wrapper
    return decorator
