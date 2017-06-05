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

    apiVersion = Attribute(
        """The Kubernetes *apiVersion* of this object.  For example, ``u"v1"``."""
    )

    metadata = Attribute(
        """
        The metadata for this object.  As either ``ObjectMetadata`` or
        ``NamespacedObjectMetadata``.
        """
    )

    def serialize():
        """
        Marshal this object to a JSON- and YAML-compatible object graph.

        :return dict: A JSON-compatible representation of this object.
            ``kind`` and ``apiVersion`` may be omitted.
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

    def versioned_client():
        """
        Create a client which will interact with the Kubernetes deployment
        represented by this object.

        Customize that client for the version of Kubernetes it will interact
        with.

        :return Deferred(IKubernetesClient): The client.
        """

    # Pending deprecation.
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
    model = Attribute(
        "The Kubernetes data model for use with this client.  This must "
        "agree with the data model used by the server with which this "
        "client will interact."
    )

    def version():
        """
        Retrieve server version information.

        :return Deferred(version.Info): The version information reported by
            the server about itself.
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


    def replace(obj):
        """
        Replace an existing object with a new one.

        :param IObject obj: The replacement object.  An old object with the
            same name in the same namespace (if applicable) will be replaced
            with this one.

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
