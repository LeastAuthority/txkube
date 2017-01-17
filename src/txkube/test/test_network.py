# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube.network_kubernetes``.

See ``get_kubernetes`` for pre-requisites.
"""

from os import environ

from twisted.python.url import URL

from ..testing.integration import kubernetes_client_tests

from .. import network_kubernetes

def get_kubernetes(case):
    """
    Create a real ``IKubernetes`` provider, taking necessary
    configuration details from the environment.

    To use this set:

      - TXKUBE_INTEGRATION_KUBERNETES_BASE_URL
    """
    try:
        base_url = environ["TXKUBE_INTEGRATION_KUBERNETES_BASE_URL"]
    except KeyError:
        case.skipTest("Cannot find TXKUBE_INTEGRATION_KUBERNETES_BASE_URL in environment.")
    else:
        return network_kubernetes(
            base_url=URL.fromText(base_url.decode("ascii")),
            credentials=None,
        )


class KubernetesClientIntegrationTests(kubernetes_client_tests(get_kubernetes)):
    """
    Integration tests which interact with a network-accessible
    Kubernetes deployment via ``txkube.network_kubernetes``.
    """
