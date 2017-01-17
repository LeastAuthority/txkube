# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube.memory_kubernetes``.
"""

from ..testing.integration import kubernetes_client_tests

from .. import memory_kubernetes

def get_kubernetes(case):
    """
    Create an in-memory test double provider of ``IKubernetes``.
    """
    return memory_kubernetes()


class KubernetesClientIntegrationTests(kubernetes_client_tests(get_kubernetes)):
    """
    Integration tests which interact with an in-memory-only Kubernetes
    deployment via ``txkube.memory_kubernetes``.
    """
