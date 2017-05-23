# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
A Kubernetes client.
"""

__all__ = [
    "version",
    "IObject", "IKubernetes", "IKubernetesClient",

    "KubernetesError", "UnrecognizedVersion", "UnrecognizedKind",

    "v1_5_model", "v1_6_model", "v1_7_model",

    "memory_kubernetes",
    "network_kubernetes",  "network_kubernetes_from_context",
    "authenticate_with_serviceaccount",
    "authenticate_with_certificate",
    "authenticate_with_certificate_chain",

    # Pending deprecation
    "v1", "v1beta1", "iobject_from_raw", "iobject_to_raw",
]

from incremental import Version

from ._metadata import version_tuple as _version_tuple
version = __version__ = Version("txkube", *_version_tuple)

from ._exception import KubernetesError, UnrecognizedVersion, UnrecognizedKind
from ._interface import IObject, IKubernetes, IKubernetesClient

from ._model import (
    v1_5_model,
    v1_6_model,
    v1_7_model,

    # Pending deprecation
    iobject_from_raw,
    iobject_to_raw,
    v1, v1beta1,
)

from ._authentication import (
    authenticate_with_serviceaccount,
    authenticate_with_certificate,
    authenticate_with_certificate_chain,
)
from ._network import network_kubernetes, network_kubernetes_from_context
from ._memory import memory_kubernetes
