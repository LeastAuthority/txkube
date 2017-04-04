# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
A Kubernetes client which uses Twisted to interact with Kubernetes
via HTTP.
"""

from os.path import expanduser
from json import loads, dumps

from zope.interface import implementer

import attr
from attr import validators

from pem import parse

from twisted.python.reflect import namedAny
from twisted.python.failure import Failure
from twisted.python.url import URL
from twisted.python.filepath import FilePath

from twisted.internet.defer import succeed

from twisted.web.iweb import IBodyProducer, IAgent
from twisted.web.http import OK, CREATED
from twisted.web.client import Agent, readBody

from eliot import Message, start_action
from eliot.twisted import DeferredContext

from pykube import KubeConfig

from . import (
    IObject, IKubernetes, IKubernetesClient, KubernetesError,
    iobject_from_raw, iobject_to_raw,
    authenticate_with_certificate,
)

def network_kubernetes(**kw):
    """
    Create a new ``IKubernetes`` provider which can be used to create clients.

    :param twisted.python.url.URL base_url: The root of the Kubernetes HTTPS
        API to interact with.

    :param twisted.web.iweb.IAgent agent: An HTTP agent to use to issue
        requests.  Defaults to a new ``twisted.web.client.Agent`` instance.
        See ``txkube.authenticate_with_serviceaccount`` and
        ``txkube.authenticate_with_certificate`` for helpers for creating
        agents that interact well with Kubernetes servers.

    :return IKubernetes: The Kubernetes service.
    """
    return _NetworkKubernetes(**kw)



def network_kubernetes_from_context(reactor, context, path=None):
    """
    Create a new ``IKubernetes`` provider based on a kube config file.

    :param reactor: A Twisted reactor which will be used for I/O and
        scheduling.

    :param unicode context: The name of the kube config context from which to
        load configuration details.

    :param FilePath path: The location of the kube config file to use.

    :return IKubernetes: The Kubernetes service described by the named
        context.
    """
    if path is None:
        path = FilePath(expanduser(u"~/.kube/config"))

    config = KubeConfig.from_file(path.path)
    context = config.contexts[context]
    cluster = config.clusters[context[u"cluster"]]
    user = config.users[context[u"user"]]

    base_url = URL.fromText(cluster[u"server"].decode("ascii"))
    [ca_cert] = parse(cluster[u"certificate-authority"].bytes())

    [client_cert] = parse(user[u"client-certificate"].bytes())
    [client_key] = parse(user[u"client-key"].bytes())

    agent = authenticate_with_certificate(
        reactor, base_url, client_cert, client_key, ca_cert,
    )

    return network_kubernetes(
        base_url=base_url,
        agent=agent,
    )


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

    def _request(self, method, url, headers=None, bodyProducer=None):
        action = start_action(
            action_type=u"network-client:request",
            method=method,
            url=url.asText(),
        )
        with action.context():
            d = self.agent.request(
                method, url.asText().encode("ascii"), headers, bodyProducer,
            )
            return DeferredContext(d).addActionFinish()


    def _get(self, url):
        return self._request(b"GET", url)


    def _delete(self, url, options):
        bodyProducer = None
        if options is not None:
            bodyProducer = _BytesProducer(dumps(iobject_to_raw(options)))
        return self._request(b"DELETE", url, bodyProducer=bodyProducer)


    def _post(self, url, obj):
        return self._request(
            b"POST", url, bodyProducer=_BytesProducer(dumps(obj)),
        )


    def _put(self, url, obj):
        return self._request(
            b"PUT", url, bodyProducer=_BytesProducer(dumps(obj)),
        )


    def create(self, obj):
        """
        Issue a I{POST} to create the given object.
        """
        action = start_action(
            action_type=u"network-client:create",
        )
        with action.context():
            url = self.kubernetes.base_url.child(*collection_location(obj))
            document = iobject_to_raw(obj)
            Message.log(submitted_object=document)
            d = DeferredContext(self._post(url, document))
            d.addCallback(check_status, (CREATED,))
            d.addCallback(readBody)
            d.addCallback(loads)
            d.addCallback(log_response_object, action)
            d.addCallback(iobject_from_raw)
            return d.addActionFinish()


    def replace(self, obj):
        """
        Issue a I{PUT} to replace an existing object with a new one.
        """
        action = start_action(
            action_type=u"network-client:replace",
        )
        with action.context():
            url = self.kubernetes.base_url.child(*object_location(obj))
            document = iobject_to_raw(obj)
            Message.log(submitted_object=document)
            d = DeferredContext(self._put(url, document))
            d.addCallback(check_status, (OK,))
            d.addCallback(readBody)
            d.addCallback(loads)
            d.addCallback(log_response_object, action)
            d.addCallback(iobject_from_raw)
            return d.addActionFinish()


    def get(self, obj):
        """
        Issue a I{GET} to retrieve the given object.

        The object must have identifying metadata such as a namespace and a
        name but other fields are ignored.
        """
        action = start_action(
            action_type=u"network-client:get",
            kind=obj.kind,
            name=obj.metadata.name,
            namespace=getattr(obj.metadata, "namespace", None),
        )
        with action.context():
            url = self.kubernetes.base_url.child(*object_location(obj))
            d = DeferredContext(self._get(url))
            d.addCallback(check_status, (OK,))
            d.addCallback(readBody)
            d.addCallback(loads)
            d.addCallback(log_response_object, action)
            d.addCallback(iobject_from_raw)
            return d.addActionFinish()


    def delete(self, obj, options=None):
        """
        Issue a I{DELETE} to delete the given object.

        :param v1.DeleteOptions options: Optional details to control some
            consequences of the deletion.
        """
        action = start_action(
            action_type=u"network-client:delete",
            kind=obj.kind,
            name=obj.metadata.name,
            namespace=getattr(obj.metadata, "namespace", None),
        )
        with action.context():
            url = self.kubernetes.base_url.child(*object_location(obj))
            d = DeferredContext(self._delete(url, options))
            d.addCallback(check_status, (OK,))
            d.addCallback(readBody)
            d.addCallback(lambda raw: None)
            return d.addActionFinish()


    def list(self, kind):
        """
        Issue a I{GET} to retrieve objects of a given kind.
        """
        action = start_action(
            action_type=u"network-client:list",
            kind=kind.kind,
            apiVersion=kind.apiVersion,
        )
        with action.context():
            url = self.kubernetes.base_url.child(*collection_location(kind))
            d = DeferredContext(self._get(url))
            d.addCallback(check_status, (OK,))
            d.addCallback(readBody)
            d.addCallback(lambda body: iobject_from_raw(loads(body)))
            return d.addActionFinish()



def object_location(obj):
    """
    Get the URL for a specific object.

    :param IObject obj: The object the URL for which to get.

    :return tuple[unicode]: Some path segments to stick on to a base URL top
        construct the location for the given object.
    """
    return collection_location(obj) + (obj.metadata.name,)



version_to_segments = {
    u"v1": (u"api", u"v1"),
    u"v1beta1": (u"apis", u"extensions", u"v1beta1"),
}


def collection_location(obj):
    """
    Get the URL for the collection of objects like ``obj``.

    :param obj: Either a type representing a Kubernetes object kind or an
        instance of such a type.

    :return tuple[unicode]: Some path segments to stick on to a base URL to
        construct the location of the collection of objects like the one
        given.
    """
    # TODO kind is not part of IObjectLoader and we should really be loading
    # apiVersion off of this object too.
    kind = obj.kind
    apiVersion = obj.apiVersion

    prefix = version_to_segments[apiVersion]

    collection = kind.lower() + u"s"

    if IObject.providedBy(obj):
        # Actual objects *could* have a namespace...
        namespace = obj.metadata.namespace
    else:
        # Types representing a kind couldn't possible.
        namespace = None

    if namespace is None:
        # If there's no namespace, look in the un-namespaced area.
        return prefix + (collection,)

    # If there is, great, look there.
    return prefix + (u"namespaces", namespace, collection)



@implementer(IKubernetes)
@attr.s(frozen=True)
class _NetworkKubernetes(object):
    """
    ``_NetworkKubernetes`` knows the location of a particular
    Kubernetes deployment and gives out clients which speak to that
    deployment.
    """
    base_url = attr.ib(validator=validators.instance_of(URL))
    _agent = attr.ib(
        default=attr.Factory(lambda: Agent(namedAny("twisted.internet.reactor"))),
    )

    def client(self):
        return _NetworkClient(self, self._agent)



def log_response_object(document, action):
    """
    Emit an Eliot log event belonging to the given action describing the given
    response.

    :param document: Anything Eliot loggable (but presumably a parsed
        Kubernetes response document).

    :param action: The Eliot action to which to attach the event.

    :return: ``document``
    """
    action.add_success_fields(response_object=document)
    return document


def check_status(response, expected):
    if response.code not in expected:
        d = KubernetesError.from_response(response)
        d.addCallback(Failure)
        return d
    return response
