# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Explicit interface definitions for txkube.
"""

from zope.interface import Attribute, Interface


class IObject(Interface):
    """
    ``IObject`` providers model `Kubernetes objects
    <https://github.com/kubernetes/community/blob/master/contributors/devel/api-conventions.md#objects>`_.
    """
    kind = Attribute(
        """The Kubernetes *kind* of this object.  For example, ``u"Namespace"``."""
    )

    metadata = Attribute(
        """
        The metadata for this object.  As either ``ObjectMetadata`` or
        ``NamespacedObjectMetadata``.
        """
    )

    def to_raw():
        """
        Marshal this object to a JSON- and YAML-compatible object graph.

        This is the inverse of ``IObjectLoader.from_raw``.

        :return dict: A JSON-compatible representation of this object.
        """



class INamespacedObject(Interface):
    """
    ``INamespacedObject`` indicates an ``IObject`` which must be put into a
    namespace.  The object's namespace can be found in the object's metadata.
    """



class IObjectLoader(Interface):
    """
    ``IObjectLoader`` providers can take a marshalled dump of a Kubernetes
    object (ie, the JSON- or YAML-compatible object graph) and create a
    corresponding ``IObject`` provider with a more convenient Python
    interface.
    """
    def from_raw(raw):
        """
        Load the ``IObject``.

        This is the inverse of ``IObject.to_raw``.
        """


class IKubernetes(Interface):
    """
    An ``IKubernetes`` provider represents a particular Kubernetes deployment.
    """
    base_url = Attribute(
        "The root of the Kubernetes HTTP API for this deployment "
        "(``twisted.python.url.URL``)."
    )
    credentials = Attribute(
        "The credentials which will grant access to use the "
        "deployment's API."
    )

    def client():
        """
        Create a client which will interact with the Kubernetes deployment
        represented by this object.

        :return IKubernetesClient: The client.
        """



class IKubernetesClient(Interface):
    """
    An ``IKubernetesClient`` provider allows access to the API of a particular
    Kubernetes deployment.
    """
    def list(kind):
        """
        Retrieve objects of the given kind.

        :param type kind: A model type representing the object kind to
            retrieve.  For example ``ConfigMap`` or ``Namespace``.

        :return Deferred(ObjectList): A collection of the matching objects.
        """


    def create(obj):
        """
        Create a new object in the given namespace.

        :param IObject obj: A description of the object to create.

        :return Deferred(IObject): A description of the created object.
        """


    def get(obj):
        """
        Get a single object.

        :param IObject obj: A description of which object to get.  The *kind*,
            *namespace*, and *name* address the specific object to retrieve.

        :return Deferred(IObject): A description of the retrieved object.
        """


    def delete(obj):
        """
        Delete a single object.

        :param IObject obj: A description of which object to delete.  The *kind*,
            *namespace*, and *name* address the specific object to delete.

        :return Deferred(None): The Deferred fires when the object has been
            deleted.
        """
