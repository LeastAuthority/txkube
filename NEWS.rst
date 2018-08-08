txkube 0.3.0 (2018-08-07)
=========================

Features
--------

- txkube now supports Python 3.6
- txkube.network_kubernetes_from_context now respects the KUBECONFIG
  environment variable if it is set and no configuration path is passed to it.
  (#127)


Misc
----

- #175, #177, #178, #179, #180, #182, #183, #185, #186, #188, #190, #195


txkube 0.2.0 (2017-06-05)
=========================

Bugfixes
--------

- Kubernetes model objects loaded indirectly now have the same behavior as
  those loaded directly. (#94)


Features
--------

- txkube.network_kubernetes_from_context can now load and authenticate with a
  client certificate chain. (#120)
- A new API, ``IKubernetesClient.versioned_client``, creates clients which
  adopt the Kubernetes object specification from the server they interact with.
  This makes it possible to interact with different versions of Kubernetes
  (with different object specifications). (#121)


txkube 0.1.0 (2017-04-10)
=========================

Features
--------

- Initial release of txkube with support for ConfigMaps, Services, Deployments,
  ReplicaSets, and Pods. (#117)
