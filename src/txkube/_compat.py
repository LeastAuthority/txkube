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



def native_string_to_bytes(s, encoding="ascii", errors="strict"):
    """
    Ensure that the native string ``s`` is converted to ``bytes``.
    """
    if not isinstance(s, str):
        raise TypeError("{} must be type str, not {}".format(s, type(s)))
    if str is bytes:
        # Python 2
        return s
    else:
        # Python 3
        return s.encode(encoding=encoding, errors=errors)



def native_string_to_unicode(s, encoding="ascii", errors="strict"):
    """
    Ensure that the native string ``s`` is converted to ``unicode``.
    """
    if not isinstance(s, str):
        raise TypeError("{} must be type str, not {}".format(s, type(s)))
    if str is unicode:
        # Python 3
        return s
    else:
        # Python 2
        return s.decode(encoding=encoding, errors=errors)
