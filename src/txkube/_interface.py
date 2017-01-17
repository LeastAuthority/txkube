# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Explicit interface definitions for txkube.
"""

from zope.interface import Attribute, Interface

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
