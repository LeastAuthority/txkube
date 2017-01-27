# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Functional structures for representing different kinds of Kubernetes
state.
"""

from uuid import uuid4
from pprint import pformat

from zope.interface import provider, implementer

from twisted.python.filepath import FilePath

from pyrsistent import (
    CheckedPVector, PClass, field, pmap_field, pset, pmap, freeze, thaw, mutant,
)

from . import IObject, IObjectLoader, INamespacedObject
from ._invariants import instance_of, provider_of
from ._swagger import Swagger

k8s_spec = Swagger.from_path(FilePath(__file__).sibling(u"kubernetes-1.5.json"))


ObjectMeta = k8s_spec.pclass_for_definition(u"v1.ObjectMeta")


class NamespaceStatus(k8s_spec.pclass_for_definition(u"v1.NamespaceStatus")):
    @classmethod
    def active(cls):
        return cls(phase=u"Active")


    @classmethod
    def terminating(cls):
        return cls(phase=u"Terminating")


    @classmethod
    def from_raw(cls, raw):
        return cls(**raw)


    def to_raw(self):
        return self.serialize()



@classmethod
@mutant
def object_from_raw(cls, raw):
    apiVersion, kind = raw.get(u"apiVersion", None), raw.get(u"kind", None)
    if (apiVersion, kind) != (None, None):
        if (apiVersion, kind) != (cls.apiVersion, cls.kind):
            raise ValueError("{} cannot load data for {}.{}".format(cls, apiVersion, kind))
        raw = raw.discard(u"apiVersion").discard(u"kind")
    return cls(**raw)



def object_to_raw(self):
    d = {
        u"kind": self.kind,
        u"apiVersion": self.apiVersion,
    }
    d.update(self.serialize())
    return d



@provider(IObjectLoader)
@implementer(IObject)
class Namespace(k8s_spec.pclass_for_definition(u"v1.Namespace", constant_fields={u"kind": u"Namespace", u"apiVersion": u"v1"})):
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
            metadata=ObjectMeta(name=name),
            status=None,
        )


    from_raw = object_from_raw
    to_raw = object_to_raw


    def fill_defaults(self):
        return self.transform(
            # TODO Also creationTimestamp, resourceVersion, maybe selfLink.
            [u"metadata", u"uid"], unicode(uuid4()),
            [u"status"], NamespaceStatus.active(),
        )



@provider(IObjectLoader)
@implementer(INamespacedObject)
@implementer(IObject)
class ConfigMap(k8s_spec.pclass_for_definition(u"v1.ConfigMap", constant_fields={u"kind": u"ConfigMap", u"apiVersion": u"v1"})):
    from_raw = object_from_raw
    to_raw = object_to_raw

    def fill_defaults(self):
        # TODO Surely some stuff to fill.
        return self



def object_sort_key(obj):
    """
    Define a predictable sort ordering for Kubernetes objects.

    This should be the same ordering that Kubernetes itself imposes.
    """
    return (
        obj.metadata.namespace,
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



@provider(IObjectLoader)
@implementer(IObject)
class ObjectCollection(PClass):
    """
    ``ObjectList`` is a collection of Kubernetes objects.

    This roughly corresponds to the `*List` Kubernetes types.  It's not clear
    this is actually more useful than a native Python collection such as a set
    but we'll try it out.

    :ivar pvector items: The objects belonging to this collection.
    """
    item_type = field(mandatory=True)
    items = _pvector_field(IObject)

    @property
    def kind(self):
        return self.item_type.kind + u"List"

    @property
    def apiVersion(self):
        return self.item_type.apiVersion

    @classmethod
    def of(cls, objtype, **kw):
        return cls(item_type=objtype, **kw)


    @classmethod
    def from_raw(cls, raw):
        kind = raw[u"kind"]
        item_kind = kind[:-len(u"List")]
        item_type = _loaders[item_kind]
        items = (
            # Unfortunately `kind` is an optional field.  Fortunately, the
            # top-level `kind` is something like `ConfigMapList` if you
            # asked for `.../configmaps/`.  So pass that down as a hint.
            any_object_from_raw(obj, item_kind)
            for obj
            in raw[u"items"]
        )
        return cls(item_type=item_type, items=items)


    def to_raw(self):
        return {
            u"kind": self.kind,
            u"apiVersion": self.apiVersion,
            u"metadata": {},
            u"items": list(
                thaw(freeze(obj.to_raw()).remove(u"kind").remove(u"apiVersion"))
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


_loaders = {
    loader.kind: loader
    for loader
    in {Namespace, ConfigMap}
}


def any_object_from_raw(raw, kind_hint=None):
    """
    Load an object of unspecified type from the raw representation of it.

    :raise KeyError: If the kind of object is unsupported.

    :return IObject: The loaded object.
    """
    kind = raw.get(u"kind", kind_hint)
    if kind is None:
        raise ValueError("Cannot decode serialized object: {}".format(pformat(raw)))
    if kind.endswith(u"List"):
        loader = ObjectCollection
    else:
        loader = _loaders[kind]
    return loader.from_raw(raw)
