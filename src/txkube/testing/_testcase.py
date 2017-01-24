# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
xUnit TestCase for txkube testing.
"""

from testtools import TestCase as TesttoolsTestCase

from ._eliot import CaptureEliotLogs


class TestCase(TesttoolsTestCase):
    """
    A base class for test cases which automatically uses the
    ``CaptureEliotLogs`` fixture.
    """
    def setUp(self):
        super(TestCase, self).setUp()
        self.useFixture(CaptureEliotLogs())

    # expectThat and Hypothesis don't communicate well about when the
    # test has failed.  Give them a little help.  These two Hypothesis
    # hooks will check for a flag that testtools sets when it thinks
    # the test has failed and turn it into something Hypothesis can
    # recognize.
    def setup_example(self):
        try:
            del self.force_failure
        except AttributeError:
            pass

    def teardown_example(self, ignored):
        if getattr(self, "force_failure", False):
            self.fail("expectation failed")
