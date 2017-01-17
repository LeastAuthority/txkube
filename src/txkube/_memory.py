# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
An in-memory implementation of the Kubernetes client interface.
"""

from zope.interface import implementer

from twisted.python.url import URL

from twisted.web.resource import Resource

from treq.testing import RequestTraversalAgent

from . import IKubernetes, network_kubernetes


def memory_kubernetes():
    """
    Create an in-memory Kubernetes-alike service.

    This serves as a places to hold state for stateful Kubernetes interactions
    allowed by ``IKubernetesClient``.  Only clients created against the same
    instance will all share state.

    :return IKubernetes: The new Kubernetes-alike service.
    """
    return _MemoryKubernetes()


@implementer(IKubernetes)
class _MemoryKubernetes(object):
    """
    ``_MemoryKubernetes`` maintains state in-memory which approximates
    the state of a real Kubernetes deployment sufficiently to expose a
    subset of the external Kubernetes API.
    """
    def __init__(self):
        base_url = URL.fromText(u"https://kubernetes.example.invalid./")
        self._resource = _kubernetes_resource()
        self._kubernetes = network_kubernetes(
            base_url=base_url,
            credentials=None,
            agent=RequestTraversalAgent(self._resource),
        )

    def client(self, *args, **kwargs):
        """
        :return IKubernetesClient: A new client which interacts with this
            object rather than a real Kubernetes deployment.
        """
        return self._kubernetes.client(*args, **kwargs)


def _kubernetes_resource():
    return Resource()
