# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Behaviorless structures for representing different kinds of Kubernetes
state.
"""

from zope.interface import implementer

from pyrsistent import CheckedPSet, PClass, field, pmap_field

from . import IObject
from ._invariants import instance_of, provider_of

class ObjectMetadata(PClass):
    items = pmap_field(unicode, unicode)

    @property
    def name(self):
        return self.items[u"name"]

    @property
    def uid(self):
        return self.items[u"uid"]


class NamespacedObjectMetadata(ObjectMetadata):
    @property
    def namespace(self):
        return self.items[u"namespace"]


@implementer(IObject)
class Namespace(PClass):
    """
    ``ConfigMap`` instances model `Kubernetes namespaces <https://kubernetes.io/docs/user-guide/namespaces/>`_.
    """
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


@implementer(IObject)
class ConfigMap(PClass):
    """
    ``ConfigMap`` instances model `ConfigMap objects
    <https://kubernetes.io/docs/api-reference/v1/definitions/#_v1_configmap>`_.
    """
    metadata = field(
        mandatory=True,
        invariant=instance_of(NamespacedObjectMetadata),
    )


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
    items = _pset_field(IObject)
