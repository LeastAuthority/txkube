# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Functional structures for representing different kinds of Kubernetes
state.
"""

from uuid import uuid4

import attr

from zope.interface import implementer

from pyrsistent import mutant

from twisted.python.filepath import FilePath

from . import UnrecognizedVersion, UnrecognizedKind, IObject
from ._swagger import Swagger, VersionedPClasses

@attr.s(frozen=True)
class _KubernetesDataModel(object):
    """
    A representation of txkube's understanding of the data model of some
    particular version of Kubernetes.
    """
    spec = attr.ib()
    version_type = attr.ib()
    version = attr.ib()

    v1 = attr.ib()
    v1beta1 = attr.ib()

    @classmethod
    def from_path(cls, path, version_type_name, version_details, v1, v1beta1):
        swagger = Swagger.from_path(path)
        spec = VersionedPClasses.transform_definitions(swagger)
        v1 = VersionedPClasses(spec, v1)
        v1beta1 = VersionedPClasses(spec, v1beta1)
        version_type = spec.pclass_for_definition(version_type_name)
        version = version_type(**version_details)
        return cls(
            spec=spec,
            version_type=version_type,
            version=version,
            v1=v1,
            v1beta1=v1beta1,
        )


    @mutant
    def iobject_from_raw(self, obj):
        """
        Load an object of unspecified type from the raw representation of it.

        :raise KeyError: If the kind of object is unsupported.

        :return IObject: The loaded object.
        """
        versions = {
            version: v
            for v in (self.v1, self.v1beta1)
            for version in v.versions
        }
        versions.update({
            "v1": self.v1,
            "v1beta1": self.v1beta1,
        })
        kind = obj[u"kind"]
        apiVersion = _unmutilate(obj[u"apiVersion"])
        try:
            v = versions[apiVersion]
        except KeyError:
            raise UnrecognizedVersion(apiVersion, obj)
        try:
            cls = getattr(v, kind)
        except AttributeError:
            raise UnrecognizedKind(apiVersion, kind, obj)
        others = obj.discard(u"kind").discard(u"apiVersion")
        return cls.create(others)


    def iobject_to_raw(self, obj):
        result = obj.serialize()
        result.update({
            u"kind": obj.kind,
            u"apiVersion": _mutilate(obj.apiVersion),
        })
        return result



# A representation of txkube's understanding of the Kubernetes 1.5 model.
v1_5_model = _KubernetesDataModel.from_path(
    FilePath(__file__).sibling(u"kubernetes-1.5.json"),
    u"version.Info", dict(
        major=u"1",
        minor=u"5",
        gitVersion=u"",
        gitCommit=u"",
        gitTreeState=u"",
        buildDate=u"",
        goVersion=u"",
        compiler=u"",
        platform=u"",
    ),
    {u"v1"},
    {u"v1beta1"},
)
iobject_to_raw = v1_5_model.iobject_to_raw
iobject_from_raw = v1_5_model.iobject_from_raw
v1 = v1_5_model.v1
v1beta1 = v1_5_model.v1beta1

# A representation of txkube's understanding of the Kubernetes 1.6 model.
v1_6_model = _KubernetesDataModel.from_path(
    FilePath(__file__).sibling(u"kubernetes-1.6.json"),
    u"io.k8s.apimachinery.pkg.version.Info", dict(
        major=u"1",
        minor=u"6",
        gitVersion=u"",
        gitCommit=u"",
        gitTreeState=u"",
        buildDate=u"",
        goVersion=u"",
        compiler=u"",
        platform=u"",
    ),
    {
        u"io.k8s.kubernetes.pkg.api.v1",
        u"io.k8s.apimachinery.pkg.apis.meta.v1",
    },
    {
        u"io.k8s.kubernetes.pkg.apis.extensions.v1beta1",
        u"io.k8s.kubernetes.pkg.apis.certificates.v1beta1",
    },
)

# A representation of txkube's understanding of the Kubernetes 1.7 model.
v1_7_model = _KubernetesDataModel.from_path(
    FilePath(__file__).sibling(u"kubernetes-1.7.json"),
    u"io.k8s.apimachinery.pkg.version.Info", dict(
        major=u"1",
        minor=u"7",
        gitVersion=u"",
        gitCommit=u"",
        gitTreeState=u"",
        buildDate=u"",
        goVersion=u"",
        compiler=u"",
        platform=u"",
    ),
    {
        u"io.k8s.kubernetes.pkg.api.v1",
        u"io.k8s.apimachinery.pkg.apis.meta.v1",
    },
    {
        u"io.k8s.kubernetes.pkg.apis.extensions.v1beta1",
        u"io.k8s.kubernetes.pkg.apis.certificates.v1beta1",
    },
)

_ALL_MODELS = [v1_5_model, v1_6_model, v1_7_model]


def set_if_none(desired_value):
    """
    Create a transformer which sets the given value if it finds ``None`` as
    the current value, otherwise leaves the current value alone.
    """
    def transform(current_value):
        if current_value is None:
            return desired_value
        return current_value
    return transform



def object_sort_key(obj):
    """
    Define a predictable sort ordering for Kubernetes objects.

    This should be the same ordering that Kubernetes itself imposes.
    """
    return (
        # Not all objects have a namespace.
        getattr(obj.metadata, "namespace", None),
        obj.metadata.name,
    )



def required_unique(objects, key):
    """
    A pyrsistent invariant which requires all objects in the given iterable to
    have a unique key.

    :param objects: The objects to check.
    :param key: A one-argument callable to compute the key of an object.

    :return: An invariant failure if any two or more objects have the same key
        computed.  An invariant success otherwise.
    """
    keys = {}
    duplicate = set()
    for k in map(key, objects):
        keys[k] = keys.get(k, 0) + 1
        if keys[k] > 1:
            duplicate.add(k)
    if duplicate:
        return (False, u"Duplicate object keys: {}".format(duplicate))
    return (True, u"")



def add(value):
    def evolver(pvector):
        return sorted(pvector.append(value), key=object_sort_key)
    return evolver



def remove(value):
    def evolver(pset):
        return pset.remove(value)
    return evolver



class _List(object):
    def __invariant__(self):
        return required_unique(self.items, object_sort_key)


    @staticmethod
    def __new__(cls, **kwargs):
        # The Kubernetes Swagger schema for Lists claims items is a *required*
        # *array*.  However, it is frequently None/null instead.  Hack around
        # such values, turning them into the empty sequence.
        #
        # It might be better to fix this with a schema overlay instead - eg,
        # with a tweak to mark them as optional instead of required.
        items = kwargs.get(u"items", None)
        if items is None:
            kwargs[u"items"] = ()
        return super(_List, cls).__new__(cls, **kwargs)


    def item_by_name(self, name):
        """
        Find an item in this collection by its name metadata.

        :param unicode name: The name of the object for which to search.

        :raise KeyError: If no object matching the given name is found.
        :return IObject: The object with the matching name.
        """
        for obj in self.items:
            if obj.metadata.name == name:
                return obj
        raise KeyError(name)


    def add(self, obj):
        return self.transform([u"items"], add(obj))


    def remove(self, obj):
        return self.transform([u"items"], remove(obj))


    def replace(self, old, new):
        return self.transform(
            [u"items"], remove(old),
            [u"items"], add(new),
        )



def define_behaviors(v):
    @v1.add_behavior_for_pclass
    class NamespaceStatus(object):
        """
        ``NamespaceStatus`` instances model `Kubernetes namespace status
        <https://kubernetes.io/docs/api-reference/v1/definitions/#_v1_namespacestatus>`_.
        """
        @classmethod
        def active(cls):
            return cls(phase=u"Active")


        @classmethod
        def terminating(cls):
            return cls(phase=u"Terminating")



    @v1.add_behavior_for_pclass
    @implementer(IObject)
    class Namespace(object):
        """
        ``Namespace`` instances model `Kubernetes namespaces
        <https://kubernetes.io/docs/user-guide/namespaces/>`_.
        """
        @classmethod
        def default(cls):
            """
            Get the default namespace.
            """
            return cls(metadata=v.v1.ObjectMeta(name=u"default"))


        def fill_defaults(self):
            return self.transform(
                # TODO Also creationTimestamp, resourceVersion, maybe selfLink.
                # Also, should this clobber existing values or leave them alone?
                # See https://github.com/LeastAuthority/txkube/issues/36
                [u"metadata", u"uid"], unicode(uuid4()),
                [u"status"], v1.NamespaceStatus.active(),
            )


        def delete_from(self, collection):
            # TODO: deletionTimestamp?  Terminating status?  See #24
            return collection.remove(self)



    @v1.add_behavior_for_pclass
    @implementer(IObject)
    class NamespaceList(_List):
        pass



    @v1.add_behavior_for_pclass
    @implementer(IObject)
    class ConfigMap(object):
        """
        ``ConfigMap`` instances model `ConfigMap objects
        <https://kubernetes.io/docs/api-reference/v1/definitions/#_v1_configmap>`_.
        """
        def fill_defaults(self):
            # TODO Surely some stuff to fill.
            # See https://github.com/LeastAuthority/txkube/issues/36
            return self


        def delete_from(self, collection):
            return collection.remove(self)



    @v1.add_behavior_for_pclass
    @implementer(IObject)
    class ConfigMapList(_List):
            pass



    @v1.add_behavior_for_pclass
    @implementer(IObject)
    class Service(object):
        """
        ``Service`` instances model `Service objects
        <https://kubernetes.io/docs/api-reference/v1/definitions/#_v1_service>`_.
        """
        def fill_defaults(self):
            # TODO Surely some stuff to fill.
            # See https://github.com/LeastAuthority/txkube/issues/36
            return self


        def delete_from(self, collection):
            return collection.remove(self)



    @v1.add_behavior_for_pclass
    @implementer(IObject)
    class ServiceList(_List):
        pass



    @v1.add_behavior_for_pclass
    @implementer(IObject)
    class Deployment(object):
        """
        ``Deployment`` instances model `Deployment objects
        <https://kubernetes.io/docs/api-reference/extensions/v1beta1/definitions/#_v1beta1_deployment>`_.
        """
        def fill_defaults(self):
            # Copying apparent Kubernetes behavior.
            return self.transform(
                [u"metadata", u"labels"],
                set_if_none(self.spec.template.metadata.labels),
            )


        def delete_from(self, collection):
            return collection.remove(self)



    @v1beta1.add_behavior_for_pclass
    @implementer(IObject)
    class DeploymentList(_List):
        pass



    @v1.add_behavior_for_pclass
    @implementer(IObject)
    class ReplicaSet(object):
        """
        ``ReplicaSet`` instances model `ReplicaSet objects
        <https://kubernetes.io/docs/concepts/workloads/controllers/replicaset/>`_.
        """
        def fill_defaults(self):
            return self


        def delete_from(self, collection):
            return collection.remove(self)



    @v1beta1.add_behavior_for_pclass
    @implementer(IObject)
    class ReplicaSetList(_List):
        pass



    @v1.add_behavior_for_pclass
    @implementer(IObject)
    class Pod(object):
        """
        ``Pod`` instances model `Pod objects
        <https://kubernetes.io/docs/api-reference/v1/definitions/#_v1_pod>`_.
        """
        def fill_defaults(self):
            return self


        def delete_from(self, collection):
            return collection.remove(self)



    @v1.add_behavior_for_pclass
    @implementer(IObject)
    class PodList(_List):
        pass



for v in _ALL_MODELS:
    define_behaviors(v)



def _mutilate(version):
    if version == u"v1beta1":
        return u"extensions/v1beta1"
    return version



def _unmutilate(version):
    if version.startswith(u"extensions/"):
        return version[len(u"extensions/"):]
    return version
