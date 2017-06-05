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


txkube 0.1.0
==========

Features
--------

- Initial release of txkube with support for ConfigMaps, Services, Deployments,
  ReplicaSets, and Pods. (#117)
