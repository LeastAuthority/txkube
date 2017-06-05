txkube
======

.. image:: http://img.shields.io/pypi/v/txkube.svg
   :target: https://pypi.python.org/pypi/txkube
   :alt: PyPI Package

.. image:: https://travis-ci.org/LeastAuthority/txkube.svg
   :target: https://travis-ci.org/LeastAuthority/txkube
   :alt: CI status

.. image:: https://codecov.io/github/LeastAuthority/txkube/coverage.svg
   :target: https://codecov.io/github/LeastAuthority/txkube
   :alt: Coverage

What is this?
-------------

txkube is a Twisted-based client library for interacting with `Kubernetes`_.

Usage Sample
------------

.. code-block:: python

   from __future__ import print_function
   from twisted.internet.task import react

   from txkube import network_kubernetes_from_context

   @react
   def main(reactor):
       k8s = network_kubernetes_from_context(reactor, u"minikube")
       d = k8s.versioned_client()
       d.addCallback(
           lambda client: client.list(client.model.v1.Namespace)
       )
       d.addCallback(print)
       return d

Installing
----------

To install the latest version of txkube using pip::

  $ pip install txkube

For additional development dependencies, install the ``dev`` extra::

  $ pip install txkube[dev]

Testing
-------

txkube uses pyunit-style tests.
After installing the development dependencies, you can run the test suite with trial::

  $ pip install txkube[dev]
  $ trial txkube

txkube also includes integration tests.
It is **not** recommended that you run these against anything but a dedicated *testing* Kubernetes cluster.
`Minikube`_ is an easy way to obtain such a thing.
Once running::

  $ pip install txkube[dev]
  $ TXKUBE_INTEGRATION_CONTEXT=minikube trial txkube

This will run the full test suite which includes the integration tests.
It will interact with (and *make destructive changes to*) the identified Kubernetes cluster.

License
-------

txkube is open source software released under the MIT License.
See the LICENSE file for more details.



.. _Kubernetes: https://kubernetes.io/
.. _Minikube: https://kubernetes.io/docs/getting-started-guides/minikube/
