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
    # kind = Attribute(
    #     """The Kubernetes *kind* of this object.  For example, ``u"Namespace"``."""
    # )
    # apiVersion = Attribute(
    #     """The Kubernetes *apiVersion* of this object.  For example, ``u"v1
    #     """
    metadata = Attribute(
        """The metadata for this object (``UnicodeToObjectPMap``)."""
    )



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
