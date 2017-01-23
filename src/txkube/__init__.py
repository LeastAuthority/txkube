# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
A Kubernetes client.
"""

__all__ = [
    "version",
    "IObject", "IObjectLoader", "IKubernetes", "IKubernetesClient",
    "network_client", "memory_client",

    "ObjectStatus",
    "ObjectMetadata", "NamespacedObjectMetadata",
    "Namespace", "ConfigMap",
    "ObjectCollection",

    "network_kubernetes", "memory_kubernetes",
]

from incremental import Version

from ._metadata import version_tuple as _version_tuple
version = Version("txkube", *_version_tuple)

from ._interface import IObject, IObjectLoader, IKubernetes, IKubernetesClient

from ._model import (
    ObjectStatus,
    ObjectMetadata, NamespacedObjectMetadata,
    Namespace, ConfigMap,
    ObjectCollection,
)

from ._network import network_kubernetes
from ._memory import memory_kubernetes
