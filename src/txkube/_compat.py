# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Helpers for Python 2/3 compatibility.
"""

from json import dumps

from twisted.python.compat import unicode

def dumps_bytes(obj):
    """
    Serialize ``obj`` to JSON formatted ``bytes``.
    """
    b = dumps(obj)
    if isinstance(b, unicode):
        b = b.encode("ascii")
    return b
