# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
A Kubernetes client.
"""

__all__ = [
    "version",
    "IObject", "IKubernetes", "IKubernetesClient",

    "v1",
    "object_from_raw",
    "iobject_from_raw",
    "iobject_to_raw",

    "ObjectCollection",

    "memory_kubernetes",
    "network_kubernetes",  "network_kubernetes_from_context",
    "authenticate_with_serviceaccount",
    "authenticate_with_certificate",
]

from incremental import Version

from ._metadata import version_tuple as _version_tuple
version = Version("txkube", *_version_tuple)

from ._interface import IObject, IKubernetes, IKubernetesClient

from ._model import (
    v1,
    object_from_raw,
    iobject_from_raw,
    iobject_to_raw,
    ObjectCollection,
)

from ._authentication import (
    authenticate_with_serviceaccount, authenticate_with_certificate,
)
from ._network import network_kubernetes, network_kubernetes_from_context
from ._memory import memory_kubernetes
