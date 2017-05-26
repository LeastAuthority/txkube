"""
Hotfix https://github.com/tobgu/pyrsistent/issues/106
"""

def detect():
    from pyrsistent import InvariantException, PClass

    class A(object):
        def __invariant__(self):
            return [(False, "")]
    class B(A):
        pass
    class C(B, PClass):
        pass

    try:
        C()
    except InvariantException:
        return False
    else:
        return True

def patch():
    from pyrsistent._checked_types import wrap_invariant
    from pyrsistent import _pclass

    def _all_dicts(bases, seen=None):
        """
        Yield each class in ``bases`` and each of their base classes.
        """
        if seen is None:
            seen = set()
        for cls in bases:
            if cls in seen:
                continue
            seen.add(cls)
            yield cls.__dict__
            for b in _all_dicts(cls.__bases__, seen):
                yield b


    def patched_store_invariants(dct, bases, destination_name, source_name):
        # Invariants are inherited
        invariants = []
        for ns in [dct] + list(_all_dicts(bases)):
            try:
                invariant = ns[source_name]
            except KeyError:
                continue
            invariants.append(invariant)

        if not all(callable(invariant) for invariant in invariants):
            raise TypeError('Invariants must be callable')
        dct[destination_name] = tuple(wrap_invariant(inv) for inv in invariants)

    _pclass.store_invariants = patched_store_invariants
