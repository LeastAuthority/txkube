# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Integration test generator for ``txkube.IKubernetesClient``.
"""

import attr

from zope.interface.verify import verifyObject

from hypothesis import given

from twisted.trial.unittest import TestCase

from .. import IKubernetesClient, Namespace
from .strategies import configmaps


def kubernetes_client_tests(get_kubernetes):
    class KubernetesClientIntegrationTests(TestCase):
        def setUp(self):
            self.kubernetes = get_kubernetes(self)
            self.client = self.kubernetes.client()


        def test_interfaces(self):
            """
            The client provides ``txkube.IKubernetesClient``.
            """
            verifyObject(IKubernetesClient, self.client)


        def test_configmap(self):
            """
            ``ConfigMap`` objects can be created and enumerated using the ``create``
            and ``enumerate`` methods of ``IKubernetesClient``.
            """
            obj = configmaps().example()
            # To avoid having to create the namespace (for now), move it to
            # the default namespace.
            # obj = attr.assoc(obj, Namespace.default())
            d = self.client.create(obj)
            def created_configmap(created):
                return self.client.enumerate(ConfigMap)
            d.addCallback(created_configmap)
            def check_configmaps(configmaps):
                self.assertEqual({obj}, configmaps)
            d.addCallback(check_configmaps)
            return d

    return KubernetesClientIntegrationTests
