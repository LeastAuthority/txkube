# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Hypothesis strategies useful for testing ``pykube``.
"""

from string import ascii_lowercase, digits

from hypothesis.strategies import (
    none, builds, fixed_dictionaries, lists, sampled_from, one_of, text,
    dictionaries, tuples,
)

from .. import v1, v1beta1

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

def joins(sep, elements):
    """
    Strategy to join unicode strings built by another strategy.

    :param unicode sep: The separate to join with.

    :param elements: A strategy which builds a sequence of unicode strings to
        join.

    :return: A strategy for building the joined strings.
    """
    return builds(
        lambda values: sep.join(values),
        elements,
    )
join = joins


def dns_labels():
    # https://github.com/kubernetes/community/blob/master/contributors/design-proposals/identifiers.md
    # https://kubernetes.io/docs/user-guide/identifiers/#names
    # https://www.ietf.org/rfc/rfc1035.txt
    letter = ascii_lowercase.decode("ascii")
    letter_digit = letter + digits.decode("ascii")
    letter_digit_hyphen = letter_digit + u"-"
    variations = [
        # Could be just one character long
        (sampled_from(letter),),
        # Or longer
        (sampled_from(letter),
         text(
             letter_digit_hyphen,
             min_size=0,
             max_size=61,
             average_size=_QUICK_AVERAGE_SIZE,
         ),
         sampled_from(letter_digit),
        ),
    ]
    return one_of(list(
        joins(u"", tuples(*alphabet))
        for alphabet
        in variations
    ))

# XXX wrong
object_name = object_names = image_names = dns_labels


def dns_subdomains():
    # XXX wrong
    return joins(
        u".",
        lists(
            dns_labels(),
            min_size=1,
            max_size=_QUICK_MAX_SIZE,
            average_size=_QUICK_AVERAGE_SIZE,
        ),
    )


def label_prefixes():
    return dns_subdomains()


def label_names():
    # https://kubernetes.io/docs/user-guide/labels/#syntax-and-character-set
    return dns_labels()


def label_values():
    # https://kubernetes.io/docs/user-guide/labels/#syntax-and-character-set
    return label_names()


def labels():
    return dictionaries(
        keys=one_of(
            join(u"/", tuples(label_prefixes(), label_names())),
            label_names(),
        ),
        values=label_values(),
        average_size=_QUICK_MAX_SIZE,
        max_size=_QUICK_MAX_SIZE,
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
            u"labels": one_of(
                none(),
                labels(),
            ),
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


def containers():
    """
    Strategy to build ``v1.Container``.
    """
    return builds(
        v1.Container,
        name=dns_labels(),
        # XXX Spec does not say image is required but it is
        image=image_names(),
    )


def podspecs():
    """
    Strategy to build ``v1.PodSpec``.
    """
    return builds(
        v1.PodSpec,
        containers=lists(
            containers(),
            min_size=1,
            average_size=_QUICK_MAX_SIZE,
            max_size=_QUICK_MAX_SIZE,
            unique_by=lambda container: container.name,
        ),
    )


def podtemplatespecs():
    """
    Strategy to build ``v1.PodTemplateSpec``.
    """
    return builds(
        v1.PodTemplateSpec,
        # v1.ObjectMeta for a PodTemplateSpec must include some labels.
        metadata=object_metadatas().filter(
            lambda meta: meta.labels and len(meta.labels) > 0,
        ),
        spec=podspecs(),
    )


def deploymentspecs():
    """
    Strategy to build ``DeploymentSpec``.
    """
    return builds(
        lambda template: v1beta1.DeploymentSpec(
            template=template,
            # The selector has to match the PodTemplateSpec.  This is an easy
            # way to accomplish that but not the only way.
            selector={u"matchLabels": template.metadata.labels},
        ),
        template=podtemplatespecs(),
    )


def deployments():
    """
    Strategy to build ``Deployment``.
    """
    return builds(
        lambda metadata, spec: v1beta1.Deployment(
            # The submitted Deployment.metadata.labels don't have to match the
            # Deployment.spec.template.metadata.labels but the server will
            # copy them up if they're missing at the top.
            metadata=metadata.set("labels", spec.template.metadata.labels),
            spec=spec,
        ),
        metadata=namespaced_object_metadatas(),
        # XXX Spec is only required if you want to be able to create the
        # Deployment.
        spec=deploymentspecs(),
    )



def services():
    """
    Strategy to build ``Service``.
    """
    return builds(
        v1.Service,
        metadata=namespaced_object_metadatas(),
    )



def _collections(cls, strategy, unique_by):
    """
    A helper for defining a strategy to build ``...List`` objects.

    :param cls: The model class to instantiate.
    :param strategy: A strategy to build elements for the collection.
    :param unique_by: A key function compatible with the ``lists`` strategy.
    """
    return builds(
        cls,
        items=one_of(
            none(),
            lists(
                strategy,
                average_size=_QUICK_AVERAGE_SIZE,
                max_size=_QUICK_MAX_SIZE,
                unique_by=unique_by,
            ),
        ),
    )


def deploymentlists():
    """
    Strategy to build ``DeploymentList``.
    """
    return _collections(v1beta1.DeploymentList, deployments(), _unique_names_with_namespaces)


def configmaplists():
    """
    Strategy to build ``ConfigMapList``.
    """
    return _collections(v1.ConfigMapList, configmaps(), _unique_names_with_namespaces)


def namespacelists(namespaces=creatable_namespaces()):
    """
    Strategy to build ``NamespaceList``.
    """
    return _collections(v1.NamespaceList, namespaces, _unique_names)


def servicelists():
    """
    Strategy to build ``ServiceList``.
    """
    return _collections(v1.ServiceList, services(), _unique_names_with_namespaces)


def objectcollections(namespaces=creatable_namespaces()):
    """
    Strategy to build ``ObjectCollection``.
    """
    return one_of(
        configmaplists(),
        namespacelists(namespaces),
        deploymentlists(),
        servicelists(),
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
        deployments(),
        services(),
        objectcollections(),
    )
