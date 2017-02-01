# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Hypothesis strategies useful for testing ``pykube``.
"""

from string import ascii_lowercase, digits

from hypothesis.strategies import (
    none, builds, fixed_dictionaries, lists, sampled_from, one_of, text,
    dictionaries,
)

from .. import v1

# Without some attempt to cap the size of collection strategies (lists,
# dictionaries), the slowness health check fails intermittently.  Here are
# some sizes for collections with no other opinion on the matter.
#
# If you write a strategy that involves a collection and there are no official
# upper limits on the number of items in that collection, you should almost
# certainly impose these limits to make sure your strategy runs quickly
# enough.
_QUICK_AVERAGE_SIZE = 3
_QUICK_MAX_SIZE = 10

def object_name():
    # https://kubernetes.io/docs/user-guide/identifiers/#names
    # [a-z0-9]([-a-z0-9]*[a-z0-9])?
    alphabet = ascii_lowercase + digits + b"-"
    return builds(
        lambda parts: b"".join(parts).decode("ascii"),
        lists(sampled_from(alphabet), min_size=1, average_size=10, max_size=253),
    ).filter(
        lambda value: not (value.startswith(b"-") or value.endswith(b"-"))
    )

def object_metadatas():
    """
    Strategy to build ``v1.ObjectMeta`` without a namespace.
    """
    return builds(
        v1.ObjectMeta.create,
        fixed_dictionaries({
            u"name": object_name(),
            u"uid": none(),
        }),
    )


def namespaced_object_metadatas():
    """
    Strategy to build ``v1.ObjectMeta`` with a namespace.
    """
    return builds(
        lambda obj_metadata, namespace: obj_metadata.set(
            u"namespace", namespace,
        ),
        obj_metadata=object_metadatas(),
        namespace=object_name(),
    )


def namespace_statuses():
    """
    Strategy to build ``Namespace.status``.
    """
    return builds(
        v1.NamespaceStatus,
        phase=sampled_from({u"Active", u"Terminating"}),
    )


def creatable_namespaces():
    """
    Strategy to build ``Namespace``\ s which can be created on a Kubernetes
    cluster.
    """
    return builds(
        v1.Namespace,
        metadata=object_metadatas(),
        status=none(),
    )


def retrievable_namespaces():
    """
    Strategy to build ``Namespace``\ s which might be retrieved from a
    Kubernetes cluster.

    This includes additional fields that might be populated by the Kubernetes
    cluster automatically.
    """
    return builds(
        lambda ns, status: ns.set(status=status),
        creatable_namespaces(),
        status=namespace_statuses(),
    )


def configmap_data_keys():
    """
    Strategy to build keys for the ``data`` mapping of a ``ConfigMap``.
    """
    return builds(
        lambda labels, dot: dot + u".".join(labels),
        labels=lists(object_name(), average_size=2, min_size=1, max_size=253//2),
        dot=sampled_from([u"", u"."]),
    ).filter(
        lambda key: len(key) <= 253
    )


def configmap_data_values():
    """
    Strategy to build values for the ``data`` field for a ``ConfigMap``.
    """
    return text()


def configmap_datas():
    """
    Strategy to build the ``data`` mapping of a ``ConfigMap``.
    """
    return one_of(
        none(),
        dictionaries(
            keys=configmap_data_keys(),
            values=configmap_data_values(),
            average_size=_QUICK_AVERAGE_SIZE,
            max_size=_QUICK_MAX_SIZE,
        ),
    )


def configmaps():
    """
    Strategy to build ``ConfigMap``.
    """
    return builds(
        v1.ConfigMap,
        metadata=namespaced_object_metadatas(),
        data=configmap_datas(),
    )


def configmaplists():
    """
    Strategy to build ``ConfigMapList``.
    """
    return builds(
        v1.ConfigMapList,
        items=lists(
            configmaps(),
            average_size=_QUICK_AVERAGE_SIZE,
            max_size=_QUICK_MAX_SIZE,
            unique_by=_unique_names_with_namespaces,
        ),
    )


def namespacelists(namespaces=creatable_namespaces()):
    """
    Strategy to build ``NamespaceList``.
    """
    return builds(
        v1.NamespaceList,
        items=lists(
            namespaces,
            average_size=_QUICK_AVERAGE_SIZE,
            max_size=_QUICK_MAX_SIZE,
            unique_by=_unique_names,
        ),
    )


def objectcollections(namespaces=creatable_namespaces()):
    """
    Strategy to build ``ObjectCollection``.
    """
    return one_of(
        configmaplists(),
        namespacelists(namespaces),
    )


def _unique_names(item):
    """
    Compute the unique key for the given (namespaceless) item within a single
    collection.
    """
    return item.metadata.name


def _unique_names_with_namespaces(item):
    """
    Compute the unique key for the given (namespaced) item within a single
    collection.
    """
    return (item.metadata.name, item.metadata.namespace)


def iobjects():
    """
    Strategy to build any one of the ``IObject`` implementations.
    """
    return one_of(
        creatable_namespaces(),
        retrievable_namespaces(),
        configmaps(),
        objectcollections(),
    )
