# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Pyrsistent invariant helpers for txkube.
"""

from twisted.python.reflect import fullyQualifiedName

def instance_of(cls):
    """
    Create an invariant requiring the value is an instance of ``cls``.
    """
    def check(value):
        return (
            isinstance(value, cls),
            u"{value!r} is instance of {actual!s}, required {required!s}".format(
                value=value,
                actual=fullyQualifiedName(type(value)),
                required=fullyQualifiedName(cls),
            ),
        )
    return check


def provider_of(iface):
    """
    Create an invariant requiring the value provides the zope.interface
    ``iface``.
    """
    def check(value):
        return (
            iface.providedBy(value),
            u"{value!r} does not provide {interface!s}".format(
                value=value,
                interface=fullyQualifiedName(iface),
            ),
        )
    return check
