# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
A Kubernetes client.
"""

__all__ = [
    "version",
    "IKubernetesClient",
    "network_client", "memory_client",
]

from incremental import Version

from ._metadata import version_tuple as _version_tuple
version = Version("txkube", *_version_tuple)

from ._interface import IKubernetes, IKubernetesClient
from ._network import network_kubernetes
from ._memory import memory_kubernetes
