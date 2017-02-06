# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Integration test generator for ``txkube.IKubernetesClient``.
"""

from operator import attrgetter, setitem
from functools import partial, wraps

from zope.interface.verify import verifyObject

from testtools.matchers import (
    AnyMatch, MatchesAll, MatchesStructure, IsInstance, Equals, Not, Contains,
    AfterPreprocessing, MatchesPredicate,
)

from testtools.twistedsupport import AsynchronousDeferredRunTest
from testtools import run_test_with

from twisted.python.failure import Failure
from twisted.internet.defer import gatherResults
from twisted.internet.task import deferLater, cooperate
from twisted.web.http import NOT_FOUND, CONFLICT

from .._network import version_to_segments

from ..testing import TestCase

from .. import (
    KubernetesError,
    IKubernetesClient,
    v1, v1beta1,
)

from .strategies import (
    creatable_namespaces, configmaps, deployments,
)


def async(f):
    def _async(*a, **kw):
        kw["timeout"] = 5.0
        return AsynchronousDeferredRunTest(*a, **kw)
    return run_test_with(_async)(f)



def matches_metadata(expected):
    return MatchesStructure(
        metadata=MatchesStructure(
            namespace=Equals(expected.namespace),
            name=Equals(expected.name),
            # TODO: It would be nice to compare labels but currently that
            # results in an annoying failure because of the confusion of
            # representation of the empty value - {} vs None.
            # https://github.com/LeastAuthority/txkube/issues/66
            # labels=Equals(expected.labels),
        ),
    )


def matches_namespace(ns):
    return matches_metadata(ns.metadata)


def matches_configmap(configmap):
    return matches_metadata(configmap.metadata)


def matches_deployment(deployment):
    return MatchesAll(
        matches_metadata(deployment.metadata),
        # Augh.  I think some kind of "expected is None or values match"
        # matcher would help?
        MatchesStructure(
            spec=MatchesStructure(
                selector=Equals(deployment.spec.selector),
                template=matches_metadata(deployment.spec.template.metadata),
            ),
        ),
    )


def has_uid():
    return MatchesStructure(
        metadata=MatchesStructure(
            uid=Not(Equals(None)),
        ),
    )


def is_active():
    return MatchesStructure(
        status=Equals(v1.NamespaceStatus.active()),
    )



def _named(kind, name, namespace=None):
    return kind(metadata=v1.ObjectMeta(name=name, namespace=namespace))



def kubernetes_client_tests(get_kubernetes):
    class KubernetesClientIntegrationTests(TestCase):
        def setUp(self):
            super(KubernetesClientIntegrationTests, self).setUp()
            self.kubernetes = get_kubernetes(self)
            self.client = self.kubernetes.client()
            self.addCleanup(self._cleanup)

        def _cleanup(self):
            pool = getattr(self.client.agent, "_pool", None)
            if pool is None:
                return None
            from twisted.internet import reactor
            return gatherResults([
                pool.closeCachedConnections(),
                # Semi-work-around for
                # https://twistedmatrix.com/trac/ticket/8998
                deferLater(reactor, 1.0, lambda: None),
            ])


        def test_interfaces(self):
            """
            The client provides ``txkube.IKubernetesClient``.
            """
            verifyObject(IKubernetesClient, self.client)


        @async
        def test_not_found(self):
            """
            ``IKubernetesClient.list`` returns a ``Deferred`` that fails with
            ``KubernetesError`` when the server responds with an HTTP NOT
            FOUND status.
            """
            # Invent a type that the server isn't going to recognize.  This
            # could happen if we're talking to a server that is missing some
            # extension we thought it had, for example.
            class Mythical(object):
                apiVersion = u"v6txkube2"
                kind = u"Mythical"
                metadata = v1.ObjectMeta()

            # The client won't know where to route the request without this.
            # There is a more general problem here that the model is missing
            # some unpredictable information about where the relevant APIs are
            # exposed in the URL hierarchy.
            version_to_segments[Mythical.apiVersion] = (
                u"apis", u"extensions", Mythical.apiVersion,
            )
            self.addCleanup(lambda: version_to_segments.pop(Mythical.apiVersion))

            d = self.client.list(Mythical)
            def failed(reason):
                self.assertThat(reason, IsInstance(Failure))
                reason.trap(KubernetesError)
                self.assertThat(
                    reason.value,
                    MatchesStructure(
                        code=Equals(NOT_FOUND),
                        status=Equals(v1.Status(
                            metadata={},
                            status=u"Failure",
                            message=u"the server could not find the requested resource",
                            reason=u"NotFound",
                            details=dict(),
                            code=NOT_FOUND,
                        )),
                    ),
                )
            d.addBoth(failed)
            return d


        @async
        def test_namespace(self):
            """
            ``Namespace`` objects can be created and retrieved using the ``create``
            and ``list`` methods of ``IKubernetesClient``.
            """
            obj = creatable_namespaces().example()
            d = self.client.create(obj)
            def created_namespace(created):
                self.assertThat(created, matches_namespace(obj))
                return self.client.list(v1.Namespace)
            d.addCallback(created_namespace)
            def check_namespaces(namespaces):
                self.assertThat(namespaces, IsInstance(v1.NamespaceList))
                # There are some built-in namespaces that we'll ignore.  If we
                # find the one we created, that's sufficient.
                self.assertThat(
                    namespaces.items,
                    AnyMatch(MatchesAll(matches_namespace(obj), has_uid(), is_active())),
                )
            d.addCallback(check_namespaces)
            return d


        def _global_object_retrieval_by_name_test(self, strategy, kind, matches):
            """
            Verify that a particular kind of non-namespaced Kubernetes object (such as
            *Namespace* or *PersistentVolume*) can be retrieved by name by
            calling ``IKubernetesClient.get`` with the ``IObject``
            corresponding to that kind as long as the object has its *name*
            metadata populated.
            """
            obj = strategy.example()
            d = self.client.create(obj)
            def created_object(created):
                return self.client.get(_named(kind, name=obj.metadata.name))
            d.addCallback(created_object)
            def got_object(retrieved):
                self.assertThat(retrieved, matches(obj))
            d.addCallback(got_object)
            return d


        def _create_duplicate_rejected_test(self, obj, kind):
            """
            Verify an object cannot be created if its name (and maybe namespace) is
            already taken.

            :param IObject obj: Some object to create.  An object with the
                same name (and namespace, if it is a namespaced *kind*) is
                expected to already have been created by the caller.

            :param unicode kind: The name of the collection of the *kind* of
                ``obj``, lowercase.  For example, *configmaps*.
            """
            # obj was already created once.
            d = self.client.create(obj)
            def failed(reason):
                self.assertThat(reason, IsInstance(Failure))
                reason.trap(KubernetesError)
                self.assertThat(
                    reason.value,
                    MatchesStructure(
                        code=Equals(CONFLICT),
                        status=Equals(v1.Status(
                            metadata={},
                            status=u"Failure",
                            # XXX This message is a little janky.  "namespaces
                            # ... already exists"?  How about "Namespace
                            # ... already exists"?  Maybe report it to
                            # Kubernetes.
                            message=u"{} \"{}\" already exists".format(kind, obj.metadata.name),
                            reason=u"AlreadyExists",
                            details=dict(
                                name=obj.metadata.name,
                                kind=kind,
                            ),
                            code=CONFLICT,
                        )),
                    ),
                )
            d.addBoth(failed)
            return d


        @async
        @needs(namespace=creatable_namespaces().example())
        def test_duplicate_configmap_rejected(self, namespace):
            """
            ``IKubernetesClient.create`` returns a ``Deferred`` that fails with
            ``KubernetesError`` if it is called with a ``ConfigMap`` object
            with the same name as a *ConfigMap* which already exists in the
            same namespace.
            """
            obj = configmaps().example()
            # Put it in the namespace that was created.
            obj = obj.transform(
                [u"metadata", u"namespace"],
                namespace.metadata.name,
            )
            d = self.client.create(obj)
            d.addCallback(
                lambda ignored: self._create_duplicate_rejected_test(
                    obj, u"configmaps"
                )
            )
            return d


        @async
        @needs(obj=creatable_namespaces().example())
        def test_duplicate_namespace_rejected(self, obj):
            """
            ``IKubernetesClient.create`` returns a ``Deferred`` that fails with
            ``KubernetesError`` if it is called with a ``Namespace`` object
            with the same name as a *Namespace* which already exists.
            """
            return self._create_duplicate_rejected_test(
                _named(v1.Namespace, name=obj.metadata.name), u"namespaces",
            )


        @async
        def test_namespace_retrieval(self):
            """
            A specific ``Namespace`` object can be retrieved by name using
            ``IKubernetesClient.get``.
            """
            return self._global_object_retrieval_by_name_test(
                creatable_namespaces(),
                v1.Namespace,
                matches_namespace,
            )


        @async
        def test_namespace_deletion(self):
            """
            ``IKubernetesClient.delete`` can be used to delete ``Namespace``
            objects.
            """
            obj = creatable_namespaces().example()
            d = self.client.create(obj)
            def created_namespace(created):
                return self.client.delete(created)
            d.addCallback(created_namespace)
            def deleted_namespace(ignored):
                return self.client.list(v1.Namespace)
            d.addCallback(deleted_namespace)
            def check_namespaces(collection):
                active = list(
                    ns.metadata.name
                    for ns
                    in collection.items
                    if ns.status.phase == u"Active"
                )
                self.assertThat(
                    active,
                    Not(Contains(obj.metadata.name)),
                )
            d.addCallback(check_namespaces)
            return d


        @async
        def test_configmap(self):
            """
            ``ConfigMap`` objects can be created and retrieved using the ``create``
            and ``list`` methods of ``IKubernetesClient``.
            """
            namespace = creatable_namespaces().example()
            # Move the object into the namespace we're going to create.
            obj = configmaps().example().transform(
                [u"metadata", u"namespace"],
                namespace.metadata.name,
            )
            d = self.client.create(namespace)
            def created_namespace(ignored):
                return self.client.create(obj)
            d.addCallback(created_namespace)
            def created_configmap(created):
                self.assertThat(created, matches_configmap(obj))
                return self.client.list(v1.ConfigMap)
            d.addCallback(created_configmap)
            def check_configmaps(collection):
                self.assertThat(collection, IsInstance(v1.ConfigMapList))
                self.assertThat(collection.items, AnyMatch(matches_configmap(obj)))
            d.addCallback(check_configmaps)
            return d


        @async
        @needs(namespace=creatable_namespaces().example())
        def test_deployment(self, namespace):
            """
            ``Deployment`` objects can be created and retrieved using the ``create``
            and ``list`` methods of ``IKubernetesClient``.
            """
            # Move the object into the namespace we've got.
            obj = deployments().example().transform(
                [u"metadata", u"namespace"],
                namespace.metadata.name,
            )
            d = self.client.create(obj)
            def created_deployment(created):
                self.assertThat(created, matches_deployment(obj))
                return self.client.list(v1beta1.Deployment)
            d.addCallback(created_deployment)
            def check_deployments(collection):
                self.assertThat(collection, IsInstance(v1beta1.DeploymentList))
                self.assertThat(collection.items, AnyMatch(matches_deployment(obj)))
            d.addCallback(check_deployments)
            return d


        @async
        def test_deployment_retrieval(self):
            """
            A specific ``Deployment`` object can be retrieved by name using
            ``IKubernetesClient.get``.
            """
            return self._namespaced_object_retrieval_by_name_test(
                deployments(),
                v1beta1.Deployment,
                matches_deployment,
            )


        @needs(namespace=creatable_namespaces().example())
        def _namespaced_object_retrieval_by_name_test(self, strategy, cls, matches, namespace):
            """
            Verify that a particular kind of namespaced Kubernetes object (such as
            *ConfigMap* or *PersistentVolumeClaim*) can be retrieved by name
            by by calling ``IKubernetesClient.get`` with the ``IObject``
            corresponding to that kind as long as the object has its *name*
            metadata populated.

            :param strategy: A Hypothesis strategy for building the namespaced
                object to create and then retrieve.

            :param cls: The ``IObject`` implementation corresponding to the
                objects ``strategy`` can build.

            :param matches: A one-argument caller which takes the expected
                object and returns a testtools matcher for it.  Since created
                objects have some unpredictable server-generated fields, this
                matcher can compare just the important, predictable parts of
                the object.

            :param v1.Namespace namespace: An existing namespace into which
                the probe object can be created.

            :return: A ``Deferred`` that fires when the behavior has been
                verified.
            """
            kind = cls.kind.lower()
            obj = strategy.example()
            # Move it to the namespace for this test.
            obj = obj.transform([u"metadata", u"namespace"], namespace.metadata.name)
            d = self.client.create(obj)
            def created_object(created):
                return self.client.get(_named(
                    cls,
                    namespace=obj.metadata.namespace, name=obj.metadata.name,
                ))
            d.addCallback(created_object)
            def got_object(retrieved):
                self.expectThat(retrieved, matches(obj))
                # Try retrieving an object with the same name but a different
                # namespace.  We shouldn't find it.
                #
                # First, compute a legal but non-existing namespace name.
                bogus_namespace = obj.metadata.namespace
                if len(bogus_namespace) > 1:
                    bogus_namespace = bogus_namespace[:-1]
                else:
                    bogus_namespace += u"x"
                return self.client.get(
                    _named(
                        cls,
                        namespace=bogus_namespace,
                        name=obj.metadata.name,
                    ),
                )
            d.addCallback(got_object)
            def check_error(reason):
                self.assertThat(reason, IsInstance(Failure))
                reason.trap(KubernetesError)
                self.assertThat(
                    reason.value,
                    MatchesStructure(
                        code=Equals(NOT_FOUND),
                        status=Equals(v1.Status(
                            metadata={},
                            status=u"Failure",
                            message=u"{}s \"{}\" not found".format(
                                kind, obj.metadata.name,
                            ),
                            reason=u"NotFound",
                            details=dict(
                                kind=u"{}s".format(kind),
                                name=obj.metadata.name,
                            ),
                            code=NOT_FOUND,
                        )),
                    ),
                )
            d.addBoth(check_error)
            return d


        @async
        def test_configmap_retrieval(self):
            """
            A specific ``ConfigMap`` object can be retrieved by name using
            ``IKubernetesClient.get``.
            """
            return self._namespaced_object_retrieval_by_name_test(
                configmaps(),
                v1.ConfigMap,
                matches_configmap,
            )


        @async
        def test_configmaps_sorted(self):
            """
            ``ConfigMap`` objects retrieved with ``IKubernetesClient.list`` appear in
            sorted order, with (namespace, name) as the sort key.
            """
            strategy = configmaps()
            objs = [strategy.example(), strategy.example()]
            ns = list(
                v1.Namespace(
                    metadata=v1.ObjectMeta(name=obj.metadata.namespace),
                    status=None,
                )
                for obj
                in objs
            )
            d = gatherResults(list(self.client.create(obj) for obj in ns + objs))
            def created_configmaps(ignored):
                return self.client.list(v1.ConfigMap)
            d.addCallback(created_configmaps)
            def check_configmaps(collection):
                self.expectThat(collection, items_are_sorted())
            d.addCallback(check_configmaps)
            return d

    return KubernetesClientIntegrationTests



def items_are_sorted():
    """
    Match an ObjectCollection if its items can be iterated in the Kubernetes
    canonical sort order - lexicographical by namespace, name.
    """
    def key(obj):
        return (
            getattr(obj.metadata, "namespace", None),
            obj.metadata.name,
        )

    def is_sorted(items, key):
        return list(items) == sorted(items, key=key)

    return AfterPreprocessing(
        attrgetter("items"),
        MatchesPredicate(
            partial(is_sorted, key=key),
            u"%s is not sorted by namespace, name",
        ),
    )


def needs(**to_create):
    """
    Create a function decorator which will create certain Kubernetes objects
    before calling the decorated function and delete them after it completes.

    This requires the decorated functions accept a first argument with a
    ``client`` attribute bound to an ``IKubernetesClient``.

    :param to_create: Keyword arguments with ``IObject`` providers as values.
        After being created, these objects will be passed to the decorated
        function using the same keyword arguments.

    :return: A function decorator.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(self, *a, **kw):
            # Check to make sure there aren't keyword argument conflicts.  I
            # doubt this is an exhaustive safety check.
            overlap = set(to_create) & set(kw)
            if overlap:
                raise TypeError(
                    "Conflict between @needs() and **kw: {}".format(overlap)
                )

            # Create the objects.
            created = {}
            task = cooperate(
                self.client.create(
                    obj
                ).addCallback(
                    partial(setitem, created, name)
                )
                for (name, obj)
                in sorted(to_create.items())
            )
            d = task.whenDone()

            # Call the decorated function.
            d.addCallback(lambda ignored: kw.update(created))
            d.addCallback(lambda ignored: f(self, *a, **kw))

            # Delete the created objects.
            def cleanup(passthrough):
                task = cooperate(
                    self.client.delete(created[name])
                    for name
                    in sorted(to_create, reverse=True)
                    if name in created
                )
                d = task.whenDone()
                d.addCallback(lambda ignored: passthrough)
                return d
            d.addBoth(cleanup)
            return d
        return wrapper
    return decorator
