# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube.network_kubernetes``.

See ``get_kubernetes`` for pre-requisites.
"""

from os import environ
from os.path import expanduser

from pem import parse

from twisted.python.url import URL

from pykube import KubeConfig

from ..testing.integration import kubernetes_client_tests

from .. import network_kubernetes, authenticate_with_certificate


def get_kubernetes(case):
    """
    Create a real ``IKubernetes`` provider, taking necessary
    configuration details from the environment.

    To use this set ``TXKUBE_INTEGRATION_CLUSTER_NAME`` to the name of a
    cluster in your ``kubectl`` configuration.  Corresponding details about
    connecting to a cluster will be loaded from that configuration.
    """
    try:
        cluster_name = environ["TXKUBE_INTEGRATION_CLUSTER_NAME"]
    except KeyError:
        case.skipTest("Cannot find TXKUBE_INTEGRATION_CLUSTER_NAME in environment.")
    else:
        config = KubeConfig.from_file(expanduser("~/.kube/config"))
        cluster = config.clusters[cluster_name]
        user = config.users[cluster_name]

        base_url = URL.fromText(cluster["server"].decode("ascii"))
        [ca_cert] = parse(cluster["certificate-authority"].bytes())

        [client_cert] = parse(user["client-certificate"].bytes())
        [client_key] = parse(user["client-key"].bytes())

        from twisted.internet import reactor
        agent = authenticate_with_certificate(
            reactor, base_url, client_cert, client_key, ca_cert,
        )

        return network_kubernetes(
            base_url=base_url,
            agent=agent,
        )


class KubernetesClientIntegrationTests(kubernetes_client_tests(get_kubernetes)):
    """
    Integration tests which interact with a network-accessible
    Kubernetes deployment via ``txkube.network_kubernetes``.
    """
