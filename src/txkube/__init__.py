# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
A Kubernetes client.
"""

__all__ = [
    "version",
    "IObject", "IKubernetes", "IKubernetesClient",

    "KubernetesError", "UnrecognizedVersion", "UnrecognizedKind",

    "openapi_to_data_model", "v1_5_model",

    "memory_kubernetes",
    "network_kubernetes",  "network_kubernetes_from_context",
    "authenticate_with_serviceaccount",
    "authenticate_with_certificate",
    "authenticate_with_certificate_chain",

    # Deprecated.
    "v1", "v1beta1", "iobject_from_raw", "iobject_to_raw",
]

from incremental import Version

from ._metadata import version_tuple as _version_tuple
version = __version__ = Version("txkube", *_version_tuple)

from ._exception import KubernetesError, UnrecognizedVersion, UnrecognizedKind
from ._interface import IObject, IKubernetes, IKubernetesClient

from ._model import (
    openapi_to_data_model, v1_5_model,

    # Deprecated.
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


def _deprecations():
    from twisted.python.deprecate import deprecatedModuleAttribute

    _0_2_0 = Version("txkube", 0, 2, 0)
    deprecatedModuleAttribute(
        _0_2_0,
        "See v1_5_model.v1 and IKubernetesClient.model.v1 instead.",
        "txkube",
        "v1",
    )
    deprecatedModuleAttribute(
        _0_2_0,
        "See v1_5_model.v1beta1 and IKubernetesClient.model.v1beta1 instead.",
        "txkube",
        "v1beta1",
    )
    deprecatedModuleAttribute(
        _0_2_0,
        "See v1_5_model.iobject_to_raw and "
        "IKubernetesClient.model.iobject_to_raw instead.",
        "txkube",
        "iobject_to_raw",
    )
    deprecatedModuleAttribute(
        _0_2_0,
        "See v1_5_model.iobject_from_raw and "
        "IKubernetesClient.model.iobject_from_raw instead.",
        "txkube",
        "iobject_from_raw",
    )

_deprecations()
del _deprecations
