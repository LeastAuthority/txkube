# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
A Kubernetes client which uses Twisted to interact with Kubernetes
via HTTP.
"""

from zope.interface import implementer

import attr
from attr import validators

from twisted.python.reflect import namedAny
from twisted.python.url import URL

from twisted.web.iweb import IAgent
from twisted.web.client import Agent

from . import IKubernetes, IKubernetesClient

def network_kubernetes(**kw):
    return _NetworkKubernetes(**kw)


@implementer(IKubernetesClient)
@attr.s(frozen=True)
class _NetworkClient(object):
    kubernetes = attr.ib(validator=validators.provides(IKubernetes))
    agent = attr.ib(validator=validators.provides(IAgent))


@implementer(IKubernetes)
@attr.s(frozen=True)
class _NetworkKubernetes(object):
    """
    ``_NetworkKubernetes`` knows the location of a particular
    Kubernetes deployment and gives out clients which speak to that
    deployment.
    """
    base_url = attr.ib(validator=validators.instance_of(URL))
    credentials = attr.ib()
    _agent = attr.ib(
        default=attr.Factory(lambda: Agent(namedAny("twisted.internet.reactor"))),
    )

    def client(self):
        return _NetworkClient(self, self._agent)
