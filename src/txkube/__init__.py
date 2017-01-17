# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
A Kubernetes client.
"""

__all__ = [
    "version",
    "IObject", "IKubernetes", "IKubernetesClient",
    "network_client", "memory_client",

    "ObjectMetadata", "NamespacedObjectMetadata", "ConfigMap",
    "Namespace", "ObjectCollection",
]

from incremental import Version

from ._metadata import version_tuple as _version_tuple
version = Version("txkube", *_version_tuple)

from ._interface import IObject, IKubernetes, IKubernetesClient

from ._model import (
    ObjectMetadata, NamespacedObjectMetadata,
    Namespace, ConfigMap,
    ObjectCollection,
)

from ._network import network_kubernetes
from ._memory import memory_kubernetes
