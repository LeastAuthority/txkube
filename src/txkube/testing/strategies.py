# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Hypothesis strategies useful for testing ``pykube``.
"""

from string import ascii_lowercase, digits

from pyrsistent import pmap

from hypothesis.strategies import none, builds, fixed_dictionaries, lists, sampled_from

from .. import ObjectMetadata, NamespacedObjectMetadata, Namespace, ConfigMap


def object_name():
    # https://kubernetes.io/docs/user-guide/identifiers/#names
    # [a-z0-9]([-a-z0-9]*[a-z0-9])?
    alphabet = ascii_lowercase + digits + b"-"
    return builds(
        lambda parts: b"".join(parts).decode("ascii"),
        lists(sampled_from(alphabet), min_size=1, average_size=10),
    ).filter(
        lambda value: not (value.startswith(b"-") or value.endswith(b"-"))
    )

def object_metadatas():
    """
    Strategy to build ``ObjectMetadata``.
    """
    return builds(
        ObjectMetadata,
        items=fixed_dictionaries({
            u"name": object_name(),
            u"uid": none(),
        }).map(pmap),
    )


def namespaced_object_metadatas():
    """
    Strategy to build ``NamespacedObjectMetadata``.
    """
    return builds(
        lambda obj_metadata, namespace: NamespacedObjectMetadata(
            items=obj_metadata.items.set(u"namespace", namespace),
        ),
        obj_metadata=object_metadatas(),
        namespace=object_name(),
    )


def namespaces():
    """
    Strategy to build ``Namespace``.
    """
    return builds(
        Namespace,
        metadata=object_metadatas(),
    )

def configmaps():
    """
    Strategy to build ``ConfigMap``.
    """
    return builds(
        ConfigMap,
        metadata=namespaced_object_metadatas(),
    )
