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
   from os import environ
   from twisted.internet.task import react
   from twisted.python.url import URL

   from txkube import Namespace, network_kubernetes, authenticate_with_serviceaccount

   @react
   def main(reactor):
       agent = authenticate_with_serviceaccount(reactor)
       base_url = URL(
           scheme=u"https",
           host=environ["KUBERNETES_SERVICE_HOST"].decode("ascii"),
           port=int(environ["KUBERNETES_SERVICE_PORT"]),
       )
       k8s = network_kubernetes(base_url=base_url, agent=agent)
       client = k8s.client()
       d = client.list(Namespace)
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
  $ TXKUBE_INTEGRATION_CLUSTER_NAME=minikube trial txkube

This will run the full test suite which includes the integration tests.
It will interact with (and *make destructive changes to*) the named Kubernetes cluster.

License
-------

txkube is open source software released under the MIT License.
See the LICENSE file for more details.



.. _Kubernetes: https://kubernetes.io/
.. _Minikube: https://kubernetes.io/docs/getting-started-guides/minikube/
