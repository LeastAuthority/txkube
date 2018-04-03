# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube._compat``.

"""

from .._compat import (
    native_string_to_bytes,
    native_string_to_unicode,
)

from ..testing import TestCase
from ..testing.matchers import raises_exception
from testtools.matchers import Equals



class NativeStringToBytesTests(TestCase):
    """
    Tests for ``native_string_to_bytes``.
    """
    def test_list(self):
        """
        Passing ``list`` as input should raise a ``TypeError``.
        """
        l = [1, 2, 3]
        self.assertThat(
            lambda: native_string_to_bytes(l),
            raises_exception(
                TypeError,
            ),
        )


    def test_none(self):
        """
        Passing ``None`` as input should raise a ``TypeError``.
        """
        self.assertRaises(
            TypeError,
            lambda: native_string_to_bytes(None),
        )


    def test_bytes_py2(self):
        """
        Passing ``bytes`` as input should return ``bytes``
        on Python 2.
        """
        if str is not bytes:
            # Python 3
            self.skipTest("skipping test on Python 3")

        self.assertThat(
            native_string_to_bytes(b"hello world"),
            Equals(b"hello world"),
        )


    def test_bytes_py3(self):
        """
        Passing ``bytes`` as input should return ``bytes`` should raise
        ``TypeError`` on Python 3.
        """
        if str is bytes:
            # Python 2
            self.skipTest("skipping test on Python 2")

        self.assertThat(
            lambda: native_string_to_bytes(b"hello world"),
            raises_exception(
                TypeError,
            ),
        )


    def test_unicode_py2(self):
        """
        Passing ``unicode`` as input should raise ``TypeError`` on Python 2.
        """
        if str is not bytes:
            # Python 3
            self.skipTest("skipping test on Python 3.")

        self.assertThat(
            lambda: native_string_to_bytes(u"hello world"),
            raises_exception(
                TypeError,
            ),
        )


    def test_unicode_py3(self):
        """
        Passing ``unicode`` as input should return ``unicode`` on Python 3.
        """
        if str is bytes:
            # Python 2
            self.skipTest(
                "native_string_to_bytes() does not accept unicode input on "
                "Python 2",
            )

        self.assertThat(
            native_string_to_bytes(u"hello world"),
            Equals(b"hello world"),
        )





class NativeStringToUnicodeTests(TestCase):
    """
    Tests for ``native_string_to_unicode``.
    """
    def test_list(self):
        """
        Passing ``list`` as input should raise a ``TypeError``.
        """
        l = [1, 2, 3]
        self.assertThat(
            lambda: native_string_to_unicode(l),
            raises_exception(
                TypeError,
            ),
        )


    def test_none(self):
        """
        Passing ``None`` as input should raise a ``TypeError``.
        """
        self.assertThat(
            lambda: native_string_to_unicode(None),
            raises_exception(
                TypeError,
            ),
        )


    def test_bytes_py2(self):
        """
        Passing ``bytes`` as input should return ``unicode`` on Python 2.
        """
        if str is not bytes:
            # Python 3
            self.skipTest("skipping test on Python 3")

        self.assertThat(
            native_string_to_unicode(b"hello world"),
            Equals(u"hello world"),
        )


    def test_bytes_py3(self):
        """
        Passing ``bytes`` as input should raise ``TypeError`` on Python 3.
        """
        if str is bytes:
            # Python 2
            self.skipTest("skipping test on Python 2")

        self.assertThat(
            lambda: native_string_to_unicode(b"hello world"),
            raises_exception(
                TypeError,
            ),
        )


    def test_unicode_py2(self):
        """
        Passing ``unicode`` as input should raise ``TypeError`` on Python 2.
        """
        if str is not bytes:
            # Python 3
            self.skipTest("skipping test on Python 3.")

        self.assertThat(
            lambda: native_string_to_unicode(u"hello world"),
            raises_exception(
                TypeError,
            ),
        )


    def test_unicode_py3(self):
        """
        Passing ``unicode`` as input should return ``unicode`` on Python 2.
        """
        if str is bytes:
            # Python 2
            self.skipTest("skipping test on Python 2")

        self.assertThat(
            native_string_to_unicode(u"hello world"),
            Equals(u"hello world"),
        )


