from zope.interface import Attribute, Interface

class IKubernetes(Interface):
    base_url = Attribute(
        "The root of the Kubernetes HTTP API for this deployment "
        "(``twisted.python.url.URL``)."
    )
    credentials = Attribute(
        "The credentials which will grant access to use the "
        "deployment's API."
    )

    def client():
        pass


class IKubernetesClient(Interface):
    pass
