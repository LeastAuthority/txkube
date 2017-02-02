# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube.network_kubernetes``.

See ``get_kubernetes`` for pre-requisites.
"""

from os import environ

from ..testing.integration import kubernetes_client_tests

from .. import network_kubernetes_from_context


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
