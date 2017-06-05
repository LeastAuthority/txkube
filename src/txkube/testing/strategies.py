# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Hypothesis strategies useful for testing ``pykube``.
"""

from string import ascii_lowercase, digits

from hypothesis.strategies import (
    none, builds, fixed_dictionaries, lists, sampled_from, one_of, text,
    dictionaries, tuples, integers, booleans,
)

from .. import v1_5_model as default_model

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
    Join unicode strings built by another strategy.

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
object_name = object_names = dns_labels


def image_names():
    """
    Build Docker image names.

    Only generate images that appear to be hosted on localhost to avoid ever
    actually pulling an image from anywhere on the network.
    """
    return dns_labels().map(lambda label: u"127.0.0.1/" + label)


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


def object_metadatas(model=default_model):
    """
    Build ``v1.ObjectMeta`` without a namespace.
    """
    return builds(
        model.v1.ObjectMeta.create,
        fixed_dictionaries({
            u"name": object_name(),
            u"uid": none(),
            u"labels": one_of(
                none(),
                labels(),
            ),
        }),
    )


def namespaced_object_metadatas(model=default_model):
    """
    Build ``v1.ObjectMeta`` with a namespace.
    """
    return builds(
        lambda obj_metadata, namespace: obj_metadata.set(
            u"namespace", namespace,
        ),
        obj_metadata=object_metadatas(model),
        namespace=object_name(),
    )


def namespace_statuses(model=default_model):
    """
    Build ``Namespace.status``.
    """
    return builds(
        model.v1.NamespaceStatus,
        phase=sampled_from({u"Active", u"Terminating"}),
    )


def creatable_namespaces(model=default_model):
    """
    Build ``Namespace``\ s which can be created on a Kubernetes cluster.
    """
    return builds(
        model.v1.Namespace,
        metadata=object_metadatas(model),
        status=none(),
    )


def retrievable_namespaces(model=default_model):
    """
    Build ``Namespace``\ s which might be retrieved from a Kubernetes cluster.

    This includes additional fields that might be populated by the Kubernetes
    cluster automatically.
    """
    return builds(
        lambda ns, status: ns.set(status=status),
        creatable_namespaces(model),
        status=namespace_statuses(model),
    )


def configmap_data_keys():
    """
    Build keys for the ``data`` mapping of a ``ConfigMap``.
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
    Build values for the ``data`` field for a ``v1.ConfigMap``.
    """
    return text()


def configmap_datas():
    """
    Build the ``data`` mapping of a ``v1.ConfigMap``.
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


def configmaps(model=default_model):
    """
    Build ``v1.ConfigMap``.
    """
    return builds(
        model.v1.ConfigMap,
        metadata=namespaced_object_metadatas(model),
        data=configmap_datas(),
    )


def containers(model=default_model):
    """
    Build ``v1.Container``.
    """
    return builds(
        model.v1.Container,
        name=dns_labels(),
        # XXX Spec does not say image is required but it is
        image=image_names(),
    )


def podspecs(model=default_model):
    """
    Build ``v1.PodSpec``.
    """
    return builds(
        model.v1.PodSpec,
        activeDeadlineSeconds=one_of(
            none(),
            # The Swagger specification claims this is an int64.  The prose
            # documentation says it must be a positive integer.  The Golang
            # PodSpec struct (pkg/api/v1/types.go:PodSpec) declares it a field
            # of type ``*int64`` - a signed type.
            integers(min_value=0, max_value=2 ** 63 - 1),
        ),
        dnsPolicy=sampled_from([u"ClusterFirst", u"Default"]),
        hostIPC=booleans(),
        hostNetwork=booleans(),
        hostPID=booleans(),
        hostname=dns_labels(),
        # And plenty more ...
        containers=lists(
            containers(model),
            min_size=1,
            average_size=_QUICK_MAX_SIZE,
            max_size=_QUICK_MAX_SIZE,
            unique_by=lambda container: container.name,
        ),
    )


def podtemplatespecs(model=default_model):
    """
    Build ``v1.PodTemplateSpec``.
    """
    return builds(
        model.v1.PodTemplateSpec,
        # v1.ObjectMeta for a PodTemplateSpec must include some labels.
        metadata=object_metadatas(model).filter(
            lambda meta: meta.labels and len(meta.labels) > 0,
        ),
        spec=podspecs(model),
    )


def _without_activeDeadlineSeconds(template):
    # When part of a Deployment or ReplicaSet, activeDeadlineSeconds may not
    # be given a value.  https://github.com/kubernetes/kubernetes/issues/38684
    return template.transform(["spec", "activeDeadlineSeconds"], None)


def replicasetspecs(model=default_model):
    """
    Build ``v1beta1.ReplicaSetSpec"".
    """
    return builds(
        lambda template, **kw: model.v1beta1.ReplicaSetSpec(
            # Make sure the selector will match Pods from the pod template
            # spec.
            selector={u"matchLabels": template.metadata.labels},
            template=template,
            **kw
        ),
        template=podtemplatespecs(model).map(_without_activeDeadlineSeconds),
        minReadySeconds=integers(min_value=0, max_value=2 ** 31 - 1),
        # Strictly speaking, the max value is more like 2 ** 31 -1.  However,
        # if we actually sent such a thing to Kubernetes we could probably
        # expect only undesirable consequences.
        replicas=integers(min_value=0, max_value=3),
    )


def replicasets(model=default_model):
    """
    Build ``v1beta1.ReplicaSet``.
    """
    return builds(
        model.v1beta1.ReplicaSet,
        metadata=object_metadatas(model),
        spec=replicasetspecs(model),
    )


def deploymentspecs(model=default_model):
    """
    Build ``v1beta1.DeploymentSpec``.
    """
    return builds(
        lambda template: model.v1beta1.DeploymentSpec(
            template=template,
            # The selector has to match the PodTemplateSpec.  This is an easy
            # way to accomplish that but not the only way.
            selector={u"matchLabels": template.metadata.labels},
        ),
        template=podtemplatespecs(model).map(_without_activeDeadlineSeconds),
    )


def deployments(model=default_model):
    """
    Build ``v1beta1.Deployment``.
    """
    return builds(
        lambda metadata, spec: model.v1beta1.Deployment(
            # The submitted Deployment.metadata.labels don't have to match the
            # Deployment.spec.template.metadata.labels but the server will
            # copy them up if they're missing at the top.
            metadata=metadata.set("labels", spec.template.metadata.labels),
            spec=spec,
        ),
        metadata=namespaced_object_metadatas(model),
        # XXX Spec is only required if you want to be able to create the
        # Deployment.
        spec=deploymentspecs(model),
    )


def podstatuses():
    """
    Build ``v1.PodStatus``.
    """
    return none()


def pods(model=default_model):
    """
    Builds ``v1.Pod``.
    """
    return builds(
        model.v1.Pod,
        metadata=namespaced_object_metadatas(model),
        spec=podspecs(model),
        status=podstatuses(),
    )


def service_ports(model=default_model):
    """
    Build ``v1.ServicePort``.
    """
    return builds(
        model.v1.ServicePort,
        port=integers(min_value=1, max_value=65535),
        # The specification doesn't document name as required, but it is.
        name=dns_labels().filter(lambda name: len(name) <= 24),
    )


def service_specs(model=default_model):
    """
    Build ``v1.ServiceSpec``.
    """
    return builds(
        model.v1.ServiceSpec,
        ports=lists(
            service_ports(model),
            min_size=1,
            max_size=_QUICK_MAX_SIZE,
            average_size=_QUICK_AVERAGE_SIZE,
            unique_by=lambda port: port.name,
        )
    )


def services(model=default_model):
    """
    Build ``v1.Service``.
    """
    return builds(
        model.v1.Service,
        metadata=namespaced_object_metadatas(model),
        # Though the specification doesn't tell us, the spec is required.
        spec=service_specs(model),
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


def deploymentlists(model=default_model):
    """
    Build ``v1beta1.DeploymentList``.
    """
    return _collections(
        model.v1beta1.DeploymentList,
        deployments(model),
        _unique_names_with_namespaces,
    )


def podlists(model=default_model):
    """
    Build ``v1.PodList``.
    """
    return _collections(
        model.v1.PodList,
        pods(model),
        _unique_names_with_namespaces,
    )


def replicasetlists(model=default_model):
    """
    Build ``v1beta1.ReplicaSetList``.
    """
    return _collections(
        model.v1beta1.ReplicaSetList,
        replicasets(model),
        _unique_names_with_namespaces,
    )


def configmaplists(model=default_model):
    """
    Build ``v1.ConfigMapList``.
    """
    return _collections(
        model.v1.ConfigMapList,
        configmaps(model),
        _unique_names_with_namespaces,
    )


def namespacelists(namespaces=creatable_namespaces(), model=default_model):
    """
    Build ``v1.NamespaceList``.
    """
    return _collections(
        model.v1.NamespaceList,
        namespaces,
        _unique_names,
    )


def servicelists(model=default_model):
    """
    Build ``v1.ServiceList``.
    """
    return _collections(
        model.v1.ServiceList,
        services(model),
        _unique_names_with_namespaces,
    )


def objectcollections(namespaces=creatable_namespaces(), model=default_model):
    """
    Build ``v1.ObjectCollection``.
    """
    return one_of(
        configmaplists(model),
        namespacelists(namespaces, model),
        deploymentlists(model),
        podlists(model),
        replicasetlists(model),
        servicelists(model),
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


def iobjects(model=default_model):
    """
    Build any one of the ``IObject`` implementations.
    """
    return one_of(
        creatable_namespaces(model),
        retrievable_namespaces(model),
        configmaps(model),
        deployments(model),
        pods(model),
        replicasets(model),
        services(model),
        objectcollections(model=model),
    )
