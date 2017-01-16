# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Hypothesis strategies useful for testing ``pykube``.
"""

from hypothesis.strategies import builds, fixed_dictionaries, text

from .. import NamespacedObjectMetadata, Namespace, ConfigMap


def namespace_name():
    return text()


def namespaced_object_metadatas():
    return builds(
        NamespacedObjectMetadata,
        fixed_dictionaries({
            u"name": namespace_name(),
        }),
    )

def configmaps():
    """
    Strategy for creating ``ConfigMap`` Kubernetes objects.
    """
    return builds(
        ConfigMap,
        metadata=namespaced_object_metadatas(),
    )
