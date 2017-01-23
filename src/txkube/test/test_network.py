# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube.network_kubernetes``.

See ``get_kubernetes`` for pre-requisites.
"""

from os import environ
from os.path import expanduser

from yaml import safe_load

from pem import parse

from twisted.python.url import URL

from ..testing.integration import kubernetes_client_tests

from .. import network_kubernetes
from .._authentication import authenticate_with_certificate

def load_config():
    with open(expanduser("~/.kube/config")) as config_file:
        config = safe_load(config_file)
    version = config["apiVersion"]
    if version != "v1":
        raise ValueError(
            "Cannot interpret configuration version {!r}".format(version)
        )
    return config


def _one_by_name(kind, items, name):
    matching = list(
        item
        for item
        in items
        if item["name"] == name
    )
    if len(matching) == 0:
        raise ValueError("{!s} {!r} not found".format(kind, name))
    if len(matching) > 1:
        raise ValueError(
            "Multiple {!s}s matched name {!r}".format(kind, name)
        )
    return matching[0]


def cluster_by_name(config, cluster_name):
    return _one_by_name(u"cluster", config["clusters"], cluster_name)[u"cluster"]


def user_by_name(config, user_name):
    return _one_by_name(u"user", config["users"], user_name)[u"user"]


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
        config = load_config()
        cluster = cluster_by_name(config, cluster_name)
        user = user_by_name(config, cluster_name)

        base_url = URL.fromText(cluster["server"].decode("ascii"))
        ca_path = cluster["certificate-authority"]
        with open(ca_path) as ca_file:
            [ca_cert] = parse(ca_file.read())

        with open(user["client-certificate"]) as cert_file:
            [client_cert] = parse(cert_file.read())
        with open(user["client-key"]) as key_file:
            [client_key] = parse(key_file.read())

        from twisted.internet import reactor
        agent = authenticate_with_certificate(
            reactor, base_url, client_cert, client_key, ca_cert,
        )

        return network_kubernetes(
            base_url=base_url,
            agent=agent,
            credentials=None,
        )


class KubernetesClientIntegrationTests(kubernetes_client_tests(get_kubernetes)):
    """
    Integration tests which interact with a network-accessible
    Kubernetes deployment via ``txkube.network_kubernetes``.
    """
