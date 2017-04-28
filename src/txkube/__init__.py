# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
A Kubernetes client.
"""

__all__ = [
    "version",
    "IObject", "IKubernetes", "IKubernetesClient",

    "KubernetesError", "UnrecognizedVersion", "UnrecognizedKind",
    "v1", "v1beta1", "iobject_from_raw", "iobject_to_raw",

    "memory_kubernetes",
    "network_kubernetes",  "network_kubernetes_from_context",
    "authenticate_with_serviceaccount",
    "authenticate_with_certificate",
    "authenticate_with_certificate_chain",
]

from incremental import Version

from ._metadata import version_tuple as _version_tuple
version = __version__ = Version("txkube", *_version_tuple)

from ._exception import KubernetesError, UnrecognizedVersion, UnrecognizedKind
from ._interface import IObject, IKubernetes, IKubernetesClient

from ._model import (
    v1, v1beta1,
    iobject_from_raw,
    iobject_to_raw,
)

from ._authentication import (
    authenticate_with_serviceaccount,
    authenticate_with_certificate,
    authenticate_with_certificate_chain,
)
from ._network import network_kubernetes, network_kubernetes_from_context
from ._memory import memory_kubernetes
