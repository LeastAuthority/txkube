# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Functional structures for representing different kinds of Kubernetes
state.
"""

from uuid import uuid4

from zope.interface import implementer

from pyrsistent import CheckedPVector, PClass, field, thaw, mutant

from twisted.python.filepath import FilePath

from . import IObject
from ._invariants import provider_of
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


    def to_raw(self):
        return self.serialize()



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


    def to_raw(self):
        result = {
            u"kind": self.kind,
            u"apiVersion": u"v1",
            u"metadata": self.metadata.serialize(),
            u"spec": {},
        }
        if self.status is not None:
            result[u"status"] = self.status.to_raw()
        return result



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


    def to_raw(self):
        result = {
            u"kind": self.kind,
            u"apiVersion": u"v1",
            u"metadata": self.metadata.serialize(),
        }
        if self.data is not None:
            # Kubernetes only includes the item if there is some data.
            #
            # XXX I'm not sure if there's a difference between no data and
            # data with no items.
            result[u"data"] = thaw(self.data)
        return result



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



def _pvector_field(iface):
    class _CheckedIObjectPVector(CheckedPVector):
        __invariant__ = provider_of(iface)

    return field(
        mandatory=True,
        type=_CheckedIObjectPVector,
        factory=lambda v: _CheckedIObjectPVector.create(sorted(v, key=object_sort_key)),
        initial=_CheckedIObjectPVector(),
    )



@implementer(IObject)
class ObjectCollection(PClass):
    """
    ``ObjectList`` is a collection of Kubernetes objects.

    This roughly corresponds to the `*List` Kubernetes types.  It's not clear
    this is actually more useful than a native Python collection such as a set
    but we'll try it out.

    :ivar pvector items: The objects belonging to this collection.
    """
    @property
    def kind(self):
        if self.items:
            return self.items[0].kind + u"List"
        return u"NamespaceList"

    apiVersion = u"v1"

    items = _pvector_field(IObject)

    @classmethod
    def from_raw(cls, raw):
        element_kind = raw[u"kind"][:-len(u"List")]
        element_version = cls.apiVersion

        items = (
            # Unfortunately `kind` is an optional field.  Fortunately, the
            # top-level `kind` is something like `ConfigMapList` if you
            # asked for `.../configmaps/`.  So pass that down as a hint.
            object_from_raw(obj, element_kind, element_version)
            for obj
            in raw[u"items"]
        )
        return cls(items=items)


    def to_raw(self):
        return {
            u"kind": self.kind,
            u"apiVersion": u"v1",
            u"metadata": {},
            u"items": list(
                obj.to_raw()
                for obj
                in self.items
            ),
        }


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


    def replace(self, old, new):
        return self.transform(
            [u"items"], remove(old),
            [u"items"], add(new),
        )



def add(value):
    def evolver(pvector):
        return sorted(pvector.append(value), key=object_sort_key)
    return evolver


def remove(value):
    def evolver(pset):
        return pset.remove(value)
    return evolver


def object_from_raw(raw, kind_hint=None, version_hint=None):
    """
    Load an object of unspecified type from the raw representation of it.

    :raise KeyError: If the kind of object is unsupported.

    :return IObject: The loaded object.
    """
    kind = raw.get(u"kind", kind_hint)
    if kind.endswith(u"List"):
        return ObjectCollection.from_raw(raw)
    return iobject_from_raw(raw, kind_hint, version_hint)


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
    kind = obj.get(u"kind", kind_hint)
    apiVersion = obj.get(u"apiVersion", version_hint)
    v = _versions[apiVersion]
    cls = getattr(v, kind)
    others = obj.discard(u"kind").discard(u"apiVersion")
    return cls.create(others)
