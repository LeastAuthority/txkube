# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube.testing.matchers``.
"""

import attr

from pyrsistent import PClass, field

from testtools.matchers import Is, Equals

from sys import version_info

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

        # The matcher has a nice string representation.
        self.expectThat(
            str(MappingEquals({})),
            Equals("MappingEquals({})"),
        )


    def test_mismatch_py2(self):
        """
        ``MappingEquals.match`` returns a mismatch when comparing two ``dict``
        which do not compare equal with ``==``.
        """
        if version_info >= (3,):
            self.skipTest("skipping test on Python 3")

        # Different types altogether.
        mismatch = MappingEquals(0).match({0: 1})
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"type mismatch:\n"
                u"reference = <type 'int'> (0)\n"
                u"actual    = <type 'dict'> ({0: 1})\n"
            ),
        )



    def test_mismatch_py3(self):
        """
        ``MappingEquals.match`` returns a mismatch when comparing two ``dict``
        which do not compare equal with ``==``.
        """
        if version_info < (3,):
            self.skipTest("skipping test on Python 2")

        # Different types altogether.
        mismatch = MappingEquals(0).match({0: 1})
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"type mismatch:\n"
                u"reference = <class 'int'> (0)\n"
                u"actual    = <class 'dict'> ({0: 1})\n"
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


    def test_equals_py2(self):
        """
        ``AttrsEquals.match`` returns ``None`` when comparing two attrs-based
        instances which compare equal with ``==``.
        """
        if version_info >= (3,):
            self.skipTest("skipping test on Python 3")
        # The matcher has a nice string representation.
        self.expectThat(
            str(AttrsEquals(self.attrs(u"bar"))),
            Equals("AttrsEquals(attrs(foo=u'bar'))"),
        )


    def test_equals_py3(self):
        """
        ``AttrsEquals.match`` returns ``None`` when comparing two attrs-based
        instances which compare equal with ``==``.
        """
        if version_info < (3,):
            self.skipTest("skipping test on Python 2")
        # The matcher has a nice string representation.
        self.expectThat(
            str(AttrsEquals(self.attrs(u"bar"))),
            Equals("AttrsEquals(AttrsEqualsTests.attrs(foo='bar'))"),
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


    def test_mismatch_py2(self):
        """
        ``AttrsEquals.match`` returns ``None`` when comparing two attrs-based
        instances which compare equal with ``==``.
        """
        if version_info >= (3,):
            self.skipTest("skipping test on Python 3")

        # Different types altogether.
        mismatch = AttrsEquals(self.attrs(0)).match(1)
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"type mismatch:\n"
                u"reference = <class 'txkube.testing.test.test_matchers.attrs'> (attrs(foo=0))\n"
                u"actual    = <type 'int'> (1)\n"
            ),
        )


    def test_mismatch_py3(self):
        """
        ``AttrsEquals.match`` returns ``None`` when comparing two attrs-based
        instances which compare equal with ``==``.
        """
        if version_info < (3,):
            self.skipTest("skipping test on Python 2")

        # Different types altogether.
        mismatch = AttrsEquals(self.attrs(0)).match(1)
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"type mismatch:\n"
                u"reference = <class 'txkube.testing.test.test_matchers.AttrsEqualsTests.attrs'> (AttrsEqualsTests.attrs(foo=0))\n"
                u"actual    = <class 'int'> (1)\n"
            ),
        )



class PClassEqualsTests(TestCase):
    """
    Tests for ``PClassEquals``.
    """
    class pclass(PClass):
        foo = field()
        bar = field()


    def test_equals(self):
        """
        ``PClassEquals.match`` returns ``None`` when comparing two PClass-based
        instances which compare equal with ``==``.
        """
        self.assertThat(
            PClassEquals(self.pclass(foo=u"bar")).match(self.pclass(foo=u"bar")),
            Is(None),
        )


    def test_equals_py2(self):
        """
        On Python 2, the str representation of ``PClassEquals`` preserves the
        'u' prefix for a unicode kwarg.
        """
        if version_info >= (3,):
            self.skipTest("skipping test on Python 3")

        # The matcher has a nice string representation.
        self.expectThat(
            str(PClassEquals(self.pclass(foo=u"bar"))),
            Equals("PClassEquals(pclass(foo=u'bar'))"),
        )


    def test_equals_py3(self):
        """
        On Python 3, the str representation of ``PClassEquals`` does not
        preserve the 'u' prefix for a unicode kwarg.
        """
        if version_info < (3,):
            self.skipTest("skipping test on Python 2")

        # The matcher has a nice string representation.
        self.expectThat(
            str(PClassEquals(self.pclass(foo=u"bar"))),
            Equals("PClassEquals(pclass(foo='bar'))"),
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


    def test_mismatch_py2(self):
        """
        ``PClassEquals.match`` returns a mismatch when comparing two ``dict``
        which do not compare equal with ``==``.  On Python 2, the reference
        should contain <type 'int'> if passed an integer argument.
        """
        if version_info >= (3,):
            self.skipTest("skipping test on Python 3")

        # Different types altogether.
        mismatch = PClassEquals(0).match(self.pclass(foo=1))
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"type mismatch:\n"
                u"reference = <type 'int'> (0)\n"
                u"actual    = <class 'txkube.testing.test.test_matchers.pclass'> (pclass(foo=1))\n"
            ),
        )



    def test_mismatch_py3(self):
        """
        ``PClassEquals.match`` returns a mismatch when comparing two ``dict``
        which do not compare equal with ``==``.
        """
        if version_info < (3,):
            self.skipTest("skipping test on Python 2")

        # Different types altogether.
        mismatch = PClassEquals(0).match(self.pclass(foo=1))
        self.expectThat(
            mismatch.describe(),
            Equals(
                u"type mismatch:\n"
                u"reference = <class 'int'> (0)\n"
                u"actual    = <class 'txkube.testing.test.test_matchers.PClassEqualsTests.pclass'> (pclass(foo=1))\n"
            ),
        )

