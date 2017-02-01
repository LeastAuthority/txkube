# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Functional structures for representing different kinds of Kubernetes
state.
"""

from uuid import uuid4

from zope.interface import implementer

from pyrsistent import mutant

from twisted.python.filepath import FilePath

from . import UnrecognizedVersion, UnrecognizedKind, IObject
from ._swagger import Swagger, VersionedPClasses

spec = Swagger.from_path(FilePath(__file__).sibling(u"kubernetes-1.5.json"))
v1 = VersionedPClasses(spec, u"v1", name_field=u"kind", version_field=u"apiVersion")


def behavior(namespace):
    """
    Create a class decorator which adds the resulting class to the given
    namespace-y thing.
    """
    def decorator(cls):
        setattr(namespace, cls.__name__, cls)
        return cls
    return decorator



@behavior(v1)
class NamespaceStatus(v1.NamespaceStatus):
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



@behavior(v1)
@implementer(IObject)
class Namespace(v1.Namespace):
    """
    ``Namespace`` instances model `Kubernetes namespaces
    <https://kubernetes.io/docs/user-guide/namespaces/>`_.
    """
    @classmethod
    def default(cls):
        """
        Get the default namespace.
        """
        return cls.named(u"default")


    @classmethod
    def named(cls, name):
        """
        Create an object with only the name metadata item.
        """
        return cls(
            metadata=v1.ObjectMeta(name=name),
            status=None,
        )


    def fill_defaults(self):
        return self.transform(
            # TODO Also creationTimestamp, resourceVersion, maybe selfLink.
            # Also, should this clobber existing values or leave them alone?
            # See https://github.com/LeastAuthority/txkube/issues/36
            [u"metadata", u"uid"], unicode(uuid4()),
            [u"status"], NamespaceStatus.active(),
        )



@behavior(v1)
@implementer(IObject)
class ConfigMap(v1.ConfigMap):
    """
    ``ConfigMap`` instances model `ConfigMap objects
    <https://kubernetes.io/docs/api-reference/v1/definitions/#_v1_configmap>`_.
    """
    @classmethod
    def named(cls, namespace, name):
        """
        Create an object with only namespace and name metadata items.
        """
        return cls(
            metadata=v1.ObjectMeta(namespace=namespace, name=name),
        )


    def fill_defaults(self):
        # TODO Surely some stuff to fill.
        # See https://github.com/LeastAuthority/txkube/issues/36
        return self



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



@behavior(v1)
@implementer(IObject)
class NamespaceList(_List, v1.NamespaceList):
    pass



@behavior(v1)
@implementer(IObject)
class ConfigMapList(v1.ConfigMapList, _List):
    pass



def iobject_to_raw(obj):
    result = obj.serialize()
    result.update({
        u"kind": obj.kind,
        u"apiVersion": obj.apiVersion,
    })
    return result


_versions = {
    u"v1": v1,
}

@mutant
def iobject_from_raw(obj, kind_hint=None, version_hint=None):
    """
    Load an object of unspecified type from the raw representation of it.

    :raise KeyError: If the kind of object is unsupported.

    :return IObject: The loaded object.
    """
    kind = obj.get(u"kind", kind_hint)
    apiVersion = obj.get(u"apiVersion", version_hint)
    try:
        v = _versions[apiVersion]
    except KeyError:
        raise UnrecognizedVersion(apiVersion, obj)
    try:
        cls = getattr(v, kind)
    except AttributeError:
        raise UnrecognizedKind(apiVersion, kind, obj)
    others = obj.discard(u"kind").discard(u"apiVersion")
    return cls.create(others)
