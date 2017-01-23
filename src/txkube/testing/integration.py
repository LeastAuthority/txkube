# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Integration test generator for ``txkube.IKubernetesClient``.
"""

import attr

from zope.interface.verify import verifyObject

from pyrsistent import pmap, pset, thaw

from hypothesis import given

from testtools.matchers import AnyMatch, MatchesStructure, IsInstance, Equals

from testtools.twistedsupport import AsynchronousDeferredRunTest
from testtools import run_test_with

from twisted.internet.defer import gatherResults
from twisted.internet.task import deferLater

from ..testing import TestCase

from .. import IKubernetesClient, Namespace, ConfigMap, ObjectCollection
from .strategies import namespaces, configmaps


def async(f):
    def _async(*a, **kw):
        kw["timeout"] = 5.0
        return AsynchronousDeferredRunTest(*a, **kw)
    return run_test_with(_async)(f)


def matches_namespace(ns):
    return MatchesStructure(
        metadata=MatchesStructure.fromExample(
            ns.metadata, "name",
        ),
    )

matches_configmap = matches_namespace


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
            obj = namespaces().example()
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
                    AnyMatch(matches_namespace(obj)),
                )
            d.addCallback(check_namespaces)
            return d


        @async
        def test_configmap(self):
            """
            ``ConfigMap`` objects can be created and retrieved using the ``create``
            and ``list`` methods of ``IKubernetesClient``.
            """
            obj = configmaps().example()
            namespace = namespaces().example()
            # Move the object into the namespace we're going to create.
            obj = obj.transform(
                [u"metadata", u"items", u"namespace"],
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
            def check_configmaps(configmaps):
                self.assertThat(configmaps, IsInstance(ObjectCollection))
                self.assertThat(configmaps.items, AnyMatch(matches_configmap(obj)))
            d.addCallback(check_configmaps)
            return d

    return KubernetesClientIntegrationTests
