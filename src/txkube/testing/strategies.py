# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Hypothesis strategies useful for testing ``pykube``.
"""

from pyrsistent import pmap

from hypothesis.strategies import builds, fixed_dictionaries, text

from .. import NamespacedObjectMetadata, Namespace, ConfigMap


def object_name():
    return text()


def object_metadatas():
    return builds(
        NamespacedObjectMetadata,
        items=fixed_dictionaries({
            u"name": object_name(),
        }).map(pmap),
    )


def namespaced_object_metadatas():
    return builds(
        lambda metadata, namespace: metadata.transform(
            ["items"], lambda items: items.set(u"namespace", namespace),
        ),
        metadata=object_metadatas(),
        namespace=object_name(),
    )

def namespaces():
    return builds(
        Namespace,
        metadata=object_metadatas(),
    )

def configmaps():
    """
    Strategy for creating ``ConfigMap`` Kubernetes objects.
    """
    return builds(
        ConfigMap,
        metadata=namespaced_object_metadatas(),
    )
