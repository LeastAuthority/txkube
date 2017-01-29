# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Integration test generator for ``txkube.IKubernetesClient``.
"""

from operator import attrgetter
from functools import partial

from zope.interface.verify import verifyObject

from testtools.matchers import (
    AnyMatch, MatchesAll, MatchesStructure, IsInstance, Equals, Not, Contains,
    AfterPreprocessing, MatchesPredicate,
)

from testtools.twistedsupport import AsynchronousDeferredRunTest
from testtools import run_test_with

from twisted.python.failure import Failure
from twisted.internet.defer import gatherResults
from twisted.internet.task import deferLater
from twisted.web.http import CONFLICT

from ..testing import TestCase

from .. import (
    KubernetesError,
    IKubernetesClient, NamespaceStatus, Namespace, ConfigMap, ObjectCollection,
    ObjectMeta,
)
from .._model import Status, StatusDetails

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
                        response=Equals(Status(
                            kind=u"Status",
                            apiVersion=u"v1",
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
            obj = creatable_namespaces().example()
            d = self.client.create(obj)
            def created_namespace(created):
                return self.client.get(Namespace.named(obj.metadata.name))
            d.addCallback(created_namespace)
            def got_namespace(namespace):
                self.assertThat(namespace, matches_namespace(obj))
            d.addCallback(got_namespace)
            return d


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
                    metadata=ObjectMeta(name=obj.metadata.namespace),
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
