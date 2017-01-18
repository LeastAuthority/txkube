# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Behaviorless structures for representing different kinds of Kubernetes
state.
"""

from zope.interface import implementer

from pyrsistent import CheckedPSet, PClass, field, pmap_field, pset, freeze, thaw

from . import IObject
from ._invariants import instance_of, provider_of


class ObjectMetadata(PClass):
    _required = pset({u"name", u"uid"})

    items = pmap_field(unicode, object)
    __invariant__ = lambda m: (
        len(m._required - pset(m.items)) == 0,
        u"Required metadata missing: {}".format(m._required - pset(m.items)),
    )

    @property
    def name(self):
        return self.items[u"name"]

    @property
    def uid(self):
        return self.items[u"uid"]


class NamespacedObjectMetadata(ObjectMetadata):
    _required = ObjectMetadata._required.add(u"namespace")

    @property
    def namespace(self):
        return self.items[u"namespace"]


@implementer(IObject)
class Namespace(PClass):
    """
    ``Namespace`` instances model `Kubernetes namespaces
    <https://kubernetes.io/docs/user-guide/namespaces/>`_.
    """
    kind = u"Namespace"

    metadata = field(
        mandatory=True,
        invariant=instance_of(ObjectMetadata),
    )

    @classmethod
    def default(cls):
        """
        Get the default namespace.
        """
        return cls(ObjectMetadata(items={u"name": u"default"}))


    @classmethod
    def from_raw(cls, raw):
        return cls(
            metadata=ObjectMetadata(
                items=freeze(raw[u"metadata"]),
            ),
        )

    def to_raw(self):
        return {
            u"kind": self.kind,
            u"apiVersion": u"v1",
            u"metadata": thaw(self.metadata.items),
            u"spec": {},
            u"status": {},
        }




@implementer(IObject)
class ConfigMap(PClass):
    """
    ``ConfigMap`` instances model `ConfigMap objects
    <https://kubernetes.io/docs/api-reference/v1/definitions/#_v1_configmap>`_.
    """
    kind = u"ConfigMap"

    metadata = field(
        mandatory=True,
        invariant=instance_of(NamespacedObjectMetadata),
    )

    @classmethod
    def from_raw(cls, raw):
        return cls(
            metadata=ObjectMetadata(
                items=freeze(raw[u"metadata"]),
            ),
        )


    def to_raw(self):
        return {
            u"kind": self.kind,
            u"apiVersion": u"v1",
            u"metadata": thaw(self.metadata.items),
            u"spec": {},
            u"status": {},
        }


def _pset_field(iface):
    class _CheckedIObjectPSet(CheckedPSet):
        __invariant__ = provider_of(iface)

    return field(
        mandatory=True,
        type=_CheckedIObjectPSet,
        factory=_CheckedIObjectPSet.create,
        initial=_CheckedIObjectPSet(),
    )


class ObjectCollection(PClass):
    """
    ``ObjectList`` is a collection of Kubernetes objects.

    This roughly corresponds to the `*List` Kubernetes types.  It's not clear
    this is actually more useful than a native Python collection such as a set
    but we'll try it out.

    :ivar pset items: The objects belonging to this collection.
    """
    kind = u"List"
    items = _pset_field(IObject)

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
        for obj in self.items:
            if obj.metadata.name == name:
                return obj
        raise KeyError(name)


    def add(self, obj):
        return self.transform([u"items"], add(obj))


def add(value):
    def evolver(pset):
        return pset.add(value)
    return evolver
