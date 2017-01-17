# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Integration test generator for ``txkube.IKubernetesClient``.
"""

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase

from .. import IKubernetesClient


def kubernetes_client_tests(get_kubernetes):
    class KubernetesClientIntegrationTests(TestCase):
        def test_interfaces(self):
            """
            The client provides ``txkube.IKubernetesClient``.
            """
            kubernetes = get_kubernetes(self)
            client = kubernetes.client()
            verifyObject(IKubernetesClient, client)

    return KubernetesClientIntegrationTests
