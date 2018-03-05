# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Helpers for Python 2/3 compatibility.
"""

from twisted.python.compat import _PY3

def encode_environ(env):
    """
    Convert a ``dict`` of ``unicode`` keys and values to ``bytes`` on Python 2,
    but return the ``dict`` unmodified on Python 3.
    """
    if _PY3:
        return env
    else:
        bytes_env = {}
        for key in env:
            bytes_env[key.encode("ascii")] = env[key].encode("ascii")
        return bytes_env
