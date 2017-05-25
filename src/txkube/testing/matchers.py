# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
testtools matchers for txkube.
"""

import operator

import attr

from pyrsistent import PClass, field

from testtools.matchers import (
    Raises,
    AfterPreprocessing,
    MatchesAll,
    IsInstance,
    MatchesStructure,
    Equals,
    Mismatch,
)


class EqualElements(object):
    """
    Match iterables for which all elements compare equal to the first element.

    For example, ``[1, 1, 1]`` matches and ``[1, 1, 2]`` does not match.

    Iterables with zero or one elements always match.
    """
    def match(self, actual):
        actual_iter = iter(actual)
        try:
            first = next(actual_iter)
        except StopIteration:
            pass
        else:
            for item in actual_iter:
                if item != first:
                    return Mismatch("{} != {}".format(first, item))
        return None



class MappingLikeEquals(PClass):
    expected = field()

    comparator = operator.eq
    mismatch_string = "!="

    def __new__(cls, expected):
        # Provide positional argument support.
        # https://github.com/tobgu/pyrsistent/issues/94
        return super(MappingLikeEquals, cls).__new__(cls, expected=expected)


    def fields(self, obj):
        raise NotImplementedError()


    def get_field(self, obj, field):
        raise NotImplementedError()


    def __str__(self):
        return "%s(%r)" % (self.__class__.__name__, self.expected)


    def match(self, actual):
        if self.comparator(actual, self.expected):
            return None
        return _MappingLikeMismatch(
            self.fields, self.get_field, actual, self.mismatch_string,
            self.expected,
        )



class MappingEquals(MappingLikeEquals):
    def fields(self, obj):
        return obj.keys()


    def get_field(self, obj, key):
        return obj[key]



class AttrsEquals(MappingLikeEquals):
    def fields(self, obj):
        return list(field.name for field in attr.fields(type(obj)))


    def get_field(self, obj, key):
        return getattr(obj, key)



class PClassEquals(MappingLikeEquals):
    def fields(self, obj):
        return obj._pclass_fields.keys()


    def get_field(self, obj, key):
        try:
            return getattr(obj, key)
        except AttributeError:
            raise KeyError(key)



class _Missing(object):
    def __repr__(self):
        return "<<missing>>"

_missing = _Missing()



class _MappingLikeMismatch(Mismatch):
    def __init__(self, get_fields, get_field, actual, mismatch_string, reference,
                 reference_on_right=True):
        self._get_fields = get_fields
        self._get_field = get_field
        self._actual = actual
        self._mismatch_string = mismatch_string
        self._reference = reference
        self._reference_on_right = reference_on_right


    def describe(self):
        if type(self._actual) != type(self._reference):
            return (
                "type mismatch:\n"
                "reference = %s (%s)\n"
                "actual    = %s (%s)\n"
            ) % (
                type(self._reference), self._reference,
                type(self._actual), self._actual,
            )

        mismatched = []
        fields = self._get_fields(self._actual)
        for a_field in sorted(fields):
            try:
                actual = self._get_field(self._actual, a_field)
            except KeyError:
                actual = _missing
            try:
                reference = self._get_field(self._reference, a_field)
            except KeyError:
                reference = _missing
            if actual != reference:
                mismatched.append(dict(
                    field=a_field,
                    actual=actual,
                    reference=reference,
                ))

        extra = set(self._get_fields(self._reference)) - set(fields)
        for a_field in sorted(extra):
            reference = self._get_field(self._reference, a_field)
            mismatched.append(dict(
                field=a_field,
                reference=reference,
                actual=_missing,
            ))

        return "field mismatch:\n" + "".join(
            "field: %(field)s\n"
            "reference = %(reference)s\n"
            "actual    = %(actual)s\n" % mismatch
            for mismatch
            in mismatched
        )



def raises_exception(cls, **attributes):
    def get_exception((type, exception, traceback)):
        return exception
    return Raises(
        AfterPreprocessing(
            get_exception,
            MatchesAll(
                IsInstance(cls),
                MatchesStructure(**{
                    k: Equals(v) for (k, v) in attributes.items()
                }),
                first_only=True,
            ),
        ),
    )



@attr.s(frozen=True)
class KubernetesObjectDeleted(object):
    """
    Match a Kubernetes object collection which does not have a particular
    object in it or has that object marked as deleted.
    """
    victim = attr.ib()

    def match(self, collection):
        def key(obj):
            return (obj.metadata.name, obj.metadata.namespace)

        victim_key = key(self.victim)
        for obj in collection.items:
            if key(obj) == victim_key:
                # It can be present in the collection as long as it is marked
                # for deletion.
                if obj.metadata.deletionTimestamp is None:
                    return Mismatch(
                        "Found {} in collection and it was not marked for "
                        "deletion.".format(
                            victim_key
                        ),
                    )
                break

        # We didn't find it or we found it marked for deletion.  It matches.
        return None
