# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
A Kubernetes client which uses Twisted to interact with Kubernetes
via HTTP.
"""

from json import loads, dumps

from pyrsistent import thaw

from zope.interface import implementer

import attr
from attr import validators

from twisted.python.reflect import namedAny
from twisted.python.url import URL
from twisted.python.failure import Failure

from twisted.internet.defer import succeed

from twisted.web.iweb import IBodyProducer, IAgent
from twisted.web.http import OK, CREATED
from twisted.web.client import Agent, readBody

from eliot import start_action
from eliot.twisted import DeferredContext

from . import (
    IKubernetes, IKubernetesClient,
    Namespace, ObjectCollection,
)

def network_kubernetes(**kw):
    return _NetworkKubernetes(**kw)


# It would be simpler to use FileBodyProducer(BytesIO(...)) but:
#
#  - https://twistedmatrix.com/trac/ticket/9003
#  - https://github.com/twisted/treq/issues/161
@implementer(IBodyProducer)
@attr.s(frozen=True)
class _BytesProducer(object):
    _data = attr.ib(validator=validators.instance_of(bytes), repr=False)

    @property
    def length(self):
        return len(self._data)

    def startProducing(self, consumer):
        consumer.write(self._data)
        return succeed(None)

    def stopProducing(self):
        pass

    def pauseProducing(self):
        pass

    def resumeProducing(self):
        pass



@implementer(IKubernetesClient)
@attr.s(frozen=True)
class _NetworkClient(object):
    _apiVersion = u"v1"

    kubernetes = attr.ib(validator=validators.provides(IKubernetes))
    agent = attr.ib(validator=validators.provides(IAgent))

    def _get(self, url):
        action = start_action(action_type=u"network-client:get")
        with action.context():
            d = self.agent.request(b"GET", url.asText().encode("ascii"))
            return DeferredContext(d).addActionFinish()


    def _post(self, url, obj):
        action = start_action(action_type=u"network-client:post")
        with action.context():
            d = self.agent.request(
                b"POST",
                url.asText().encode("ascii"),
                bodyProducer=_BytesProducer(dumps(obj)),
            )
            return DeferredContext(d).addActionFinish()


    def create(self, obj):
        """
        Issue a I{POST} to create the given object.
        """
        action = start_action(action_type=u"network-client:create")
        with action.context():
            url = self.kubernetes.base_url.child(*collection_location(obj))
            document = {
                u"metadata": thaw(obj.metadata.items),
            }
            d = DeferredContext(self._post(url, document))
            d.addCallback(check_status)
            d.addCallback(readBody)
            d.addCallback(loads)
            d.addCallback(Namespace.from_raw)
            return d.addActionFinish()


    def list(self, kind):
        """
        Issue a I{GET} to retrieve objects of a given kind.
        """
        action = start_action(action_type=u"network-client:list")
        with action.context():
            url = self.kubernetes.base_url.child(*collection_location(kind))
            d = DeferredContext(self._get(url))
            d.addCallback(check_status)
            d.addCallback(readBody)
            d.addCallback(loads)
            def get_namespaces(result):
                return ObjectCollection(
                    items=(
                        Namespace.from_raw(obj)
                        for obj
                        in result[u"items"]
                    ),
                )
            d.addCallback(get_namespaces)
            return d.addActionFinish()


def collection_location(obj):
    """
    Get the URL for the collection of objects like ``obj``.

    :param obj: Either a type representing a Kubernetes object kind or an
        instance of such a type.

    :return tuple[unicode]: Some path segments to stick on to a base URL to
        construct the location of the collection of objects like the one
        given.
    """
    collection = obj.kind.lower() + u"s"
    try:
        namespace = obj.metadata.namespace
    except AttributeError:
        return (u"api", u"v1", collection, u"")
    return (u"api", u"v1", u"namespaces", namespace, collection, u"")


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


def check_status(response):
    if response.code not in (OK, CREATED):
        d = readBody(response)
        d.addCallback(lambda body: Failure(Exception(body)))
        return d
    return response
