txkube
======

.. image:: http://img.shields.io/pypi/v/txkube.svg
   :target: https://pypi.python.org/pypi/txkube
   :alt: PyPI Package

.. image:: https://travis-ci.org/twisted/txkube.svg
   :target: https://travis-ci.org/twisted/txkube
   :alt: CI status

.. image:: https://codecov.io/github/twisted/txkube/coverage.svg
   :target: https://codecov.io/github/twisted/txkube
   :alt: Coverage

What is this?
-------------

txkube is a Twisted-based client library for interacting with `Kubernetes`_.

Usage Sample
------------

.. code-block:: python

   from __future__ import print_function
   from twisted.internet.task import react
   from txkube import network_kubernetes

   @react
   def main(reactor):
       k8s = network_kubernetes(base_url=URL.fromText(u"https://kubernetes/"))
       client = k8s.client()
       d = client.list_deployments()
       d.addCallback(print)
       return d


License
-------

txkube is open source software released under the MIT License.
See the LICENSE file for more details.



.. _Kubernetes: https://kubernetes.io/
