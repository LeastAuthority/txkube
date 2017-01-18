# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
xUnit TestCase for txkube testing.
"""

from fixtures import Fixture

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
