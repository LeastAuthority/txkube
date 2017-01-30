# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
A Kubernetes client.
"""

__all__ = [
    "version",
    "IObject", "IObjectLoader", "IKubernetes", "IKubernetesClient",
    "network_client", "memory_client",

    "v1",
    "ObjectMeta",
    "object_from_raw",
    "ConfigMap",
    "ObjectCollection",

    "network_kubernetes", "memory_kubernetes",
    "authenticate_with_serviceaccount",
    "authenticate_with_certificate",
]

from incremental import Version

from ._metadata import version_tuple as _version_tuple
version = Version("txkube", *_version_tuple)

from ._interface import IObject, IObjectLoader, IKubernetes, IKubernetesClient

from ._model import (
    v1,
    object_from_raw,
    ConfigMap,
    ObjectCollection,
)

from ._network import network_kubernetes
from ._memory import memory_kubernetes
from ._authentication import (
    authenticate_with_serviceaccount, authenticate_with_certificate,
)
