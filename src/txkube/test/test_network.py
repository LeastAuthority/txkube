# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube.network_kubernetes``.

See ``get_kubernetes`` for pre-requisites.
"""

from os import environ

from zope.interface import implementer
from zope.interface.verify import verifyClass

from testtools.matchers import AnyMatch, ContainsDict, Equals

from eliot.testing import capture_logging

from twisted.test.proto_helpers import MemoryReactor
from twisted.python.url import URL
from twisted.web.client import Agent

from ..testing import TestCase
from ..testing.integration import kubernetes_client_tests

from .. import (
    IObject, v1, network_kubernetes, network_kubernetes_from_context,
)

from .._network import collection_location


def get_kubernetes(case):
    """
    Create a real ``IKubernetes`` provider, taking necessary
    configuration details from the environment.

    To use this set ``TXKUBE_INTEGRATION_CONTEXT`` to a context in your
    ``kubectl`` configuration.  Corresponding details about connecting to a
    cluster will be loaded from that configuration.
    """
    try:
        context = environ["TXKUBE_INTEGRATION_CONTEXT"]
    except KeyError:
        case.skipTest("Cannot find TXKUBE_INTEGRATION_CONTEXT in environment.")
    else:
        from twisted.internet import reactor
        return network_kubernetes_from_context(reactor, context)


class KubernetesClientIntegrationTests(kubernetes_client_tests(get_kubernetes)):
    """
    Integration tests which interact with a network-accessible
    Kubernetes deployment via ``txkube.network_kubernetes``.
    """



class CollectionLocationTests(TestCase):
    """
    Tests for ``collection_location``.
    """
    def _test_collection_location(self, version, kind, expected, namespace, instance):
        """
        Verify that ``collection_location`` for a particular version, kind,
        namespace, and Python object.

        :param unicode version: The *apiVersion* of the object to test.
        :param unicode kind: The *kind* of the object to test.

        :param tuple[unicode] expected: A representation of the path of the
            URL which should be produced.

        :param namespace: The namespace the Python object is to claim - a
            ``unicode`` string or ``None``.

        :param bool instance: Whether to make the Python object an instance
            (``True``) or a class (``False``)..
        """
        k = kind
        n = namespace
        @implementer(IObject)
        class Mythical(object):
            apiVersion = version
            kind = k

            metadata = v1.ObjectMeta(namespace=n)

            def serialize(self):
                return {}

        verifyClass(IObject, Mythical)

        if instance:
            o = Mythical()
        else:
            o = Mythical

        self.assertThat(
            collection_location(o),
            Equals(expected),
        )


    def test_v1_type(self):
        """
        ``collection_location`` returns a tuple representing an URL path like
        */api/v1/<kind>s* when called with an ``IObject`` implementation of a
        *v1* Kubernetes object kind.
        """
        self._test_collection_location(
            u"v1", u"Mythical", (u"api", u"v1", u"mythicals"),
            namespace=None,
            instance=False,
        )


    def test_v1_instance(self):
        """
        ``collection_location`` returns a tuple representing an URL path like
        */api/v1/namespace/<namespace>/<kind>s* when called with an
        ``IObject`` provider representing Kubernetes object of a *v1* kind.
        """
        self._test_collection_location(
            u"v1", u"Mythical",
            (u"api", u"v1", u"namespaces", u"ns", u"mythicals"),
            namespace=u"ns",
            instance=True,
        )


    def test_v1beta1_type(self):
        """
        ``collection_location`` returns a tuple representing an URL path like
        */apis/extensions/v1beta1/<kind>s* when called with an ``IObject``
        implementation of a *v1beta1* Kubernetes object kind.
        """
        self._test_collection_location(
            u"v1beta1", u"Mythical",
            (u"apis", u"extensions", u"v1beta1", u"mythicals"),
            namespace=None,
            instance=False,
        )


    def test_v1beta1_instance(self):
        """
        ``collection_location`` returns a tuple representing an URL path like
        */apis/extensions/v1beta1/<kind>s* when called with an ``IObject``
        implementation of a *v1beta1* Kubernetes object kind.
        """
        self._test_collection_location(
            u"v1beta1", u"Mythical",
            (u"apis", u"extensions", u"v1beta1", u"namespaces", u"ns",
             u"mythicals"),
            namespace=u"ns",
            instance=True,
        )


class ExtraNetworkClientTests(TestCase):
    """
    Direct tests for ``_NetworkClient`` that go beyond the guarantees of
    ``IKubernetesClient``.
    """
    @capture_logging(
        lambda self, logger: self.expectThat(
            logger.messages,
            AnyMatch(ContainsDict({
                u"action_type": Equals(u"network-client:list"),
                u"apiVersion": Equals(u"v1"),
                u"kind": Equals(u"Pod"),
            })),
        ),
    )
    def test_list_logging(self, logger):
        """
        ``_NetworkClient.list`` logs an Eliot event describing its given type.
        """
        client = network_kubernetes(
            base_url=URL.fromText(u"http://127.0.0.1/"),
            agent=Agent(MemoryReactor()),
        ).client()
        client.list(v1.Pod)
