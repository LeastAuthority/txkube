# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube.testing.matchers``.
"""

import attr

from pyrsistent import PClass, field

from testtools.matchers import Is, Equals

from .. import TestCase
from ..matchers import MappingEquals, AttrsEquals, PClassEquals


class MappingEqualsTests(TestCase):
    """
    Tests for ``MappingEquals``.
    """
    def test_equals(self):
        """
        ``MappingEquals.match`` returns ``None`` when comparing two ``dict`` which
        compare equal with ``==``.
        """
        self.assertThat(
            MappingEquals({u"foo": u"bar"}).match({u"foo": u"bar"}),
            Is(None),
        )


    def test_mismatch(self):
        """
        ``MappingEquals.match`` returns a mismatch when comparing two ``dict``
        which do not compare equal with ``==``.
        """
        # Same keys, different value.
        mismatch = MappingEquals({u"foo": u"bar"}).match({u"foo": u"baz"})
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"field mismatch:\n"
                u"field: foo\n"
                u"reference = bar\n"
                u"actual    = baz\n"
            ),
        )

        # Different types altogether.
        mismatch = MappingEquals(object()).match({u"foo": u"baz"})
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"type mismatch:\n"
                u"reference = <type 'object'>\n"
                u"actual    = <type 'dict'>\n"
            ),
        )

        # Actual value missing a key.
        mismatch = MappingEquals({u"foo": u"bar"}).match({})
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"field mismatch:\n"
                u"field: foo\n"
                u"reference = bar\n"
                u"actual    = <<missing>>\n"
            ),
        )

        # Expected value missing a key.
        mismatch = MappingEquals({}).match({u"foo": u"baz"})
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"field mismatch:\n"
                u"field: foo\n"
                u"reference = <<missing>>\n"
                u"actual    = baz\n"
            ),
        )



class AttrsEqualsTests(TestCase):
    """
    Tests for ``AttrsEquals``.
    """
    @attr.s
    class attrs(object):
        foo = attr.ib()


    def test_equals(self):
        """
        ``AttrsEquals.match`` returns ``None`` when comparing two attrs-based
        instances which compare equal with ``==``.
        """
        self.assertThat(
            AttrsEquals(self.attrs(u"bar")).match(self.attrs(u"bar")),
            Is(None),
        )


    def test_mismatch(self):
        """
        ``AttrsEquals.match`` returns a mismatch when comparing two attrs-based
        instances which do not compare equal with ``==``.
        """
        # Different value for the single attribute.
        mismatch = AttrsEquals(self.attrs(u"bar")).match(self.attrs(u"baz"))
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"field mismatch:\n"
                u"field: foo\n"
                u"reference = bar\n"
                u"actual    = baz\n"
            ),
        )

        # Different types altogether.
        mismatch = AttrsEquals(self.attrs(u"bar")).match(object())
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"type mismatch:\n"
                u"reference = <class 'txkube.testing.test.test_matchers.attrs'>\n"
                u"actual    = <type 'object'>\n"
            ),
        )



class PClassEqualsTests(TestCase):
    """
    Tests for ``PClassEquals``.
    """
    class pclass(PClass):
        foo = field()


    def test_equals(self):
        """
        ``PClassEquals.match`` returns ``None`` when comparing two PClass-based
        instances which compare equal with ``==``.
        """
        self.assertThat(
            PClassEquals(self.pclass(foo=u"bar")).match(self.pclass(foo=u"bar")),
            Is(None),
        )


    def test_mismatch(self):
        """
        ``PClassEquals.match`` returns a mismatch when comparing two ``dict``
        which do not compare equal with ``==``.
        """
        # Same attributes, different value.
        mismatch = PClassEquals(self.pclass(foo=u"bar")).match(self.pclass(foo=u"baz"))
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"field mismatch:\n"
                u"field: foo\n"
                u"reference = bar\n"
                u"actual    = baz\n"
            ),
        )

        # Different types altogether.
        mismatch = PClassEquals(object()).match(self.pclass(foo=u"baz"))
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"type mismatch:\n"
                u"reference = <type 'object'>\n"
                u"actual    = <class 'txkube.testing.test.test_matchers.pclass'>\n"
            ),
        )

        # Actual value missing an attribute.
        mismatch = PClassEquals(self.pclass(foo=u"bar")).match(self.pclass())
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"field mismatch:\n"
                u"field: foo\n"
                u"reference = bar\n"
                u"actual    = <<missing>>\n"
            ),
        )

        # Expected value missing an attribute.
        mismatch = PClassEquals(self.pclass()).match(self.pclass(foo=u"baz"))
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"field mismatch:\n"
                u"field: foo\n"
                u"reference = <<missing>>\n"
                u"actual    = baz\n"
            ),
        )
