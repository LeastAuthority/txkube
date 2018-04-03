# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
xUnit TestCase for txkube testing.
"""

from os import environ

from hypothesis import (
    HealthCheck,
    settings,
)

from fixtures import CompoundFixture

from testtools import TestCase as TesttoolsTestCase
from testtools.twistedsupport import AsynchronousDeferredRunTest

from twisted.python.failure import Failure

from ._eliot import CaptureEliotLogs


def _setup_hypothesis():
    settings.register_profile(
        "ci",
        suppress_health_check=[
            # CPU resources available to CI builds typically varies
            # significantly from run to run making it difficult to determine
            # if "too slow" data generation is a result of the code or the
            # execution environment.  Prevent these checks from
            # (intermittently) failing tests that are otherwise fine.
            HealthCheck.too_slow,
        ],
        # By the same reasoning as above, disable the deadline check.
        deadline=None,
    )
    settings.load_profile(environ.get("TXKUBE_HYPOTHESIS_PROFILE", "default"))
_setup_hypothesis()


class AsynchronousDeferredRunTest(AsynchronousDeferredRunTest):
    """
    An asynchronous runner supporting Eliot.
    """
    def _get_log_fixture(self):
        """
        Add ``CaptureEliotLogs`` to the log fixtures which receive special
        treatment so as to be "cleaned up" in the timeout case.

        This ensures eliot logs are reported when tests time out - something
        that will not happen using the normal ``useFixture`` API.

        See <https://bugs.launchpad.net/testtools/+bug/897196>.
        """
        return CompoundFixture([
            super(AsynchronousDeferredRunTest, self)._get_log_fixture(),
            CaptureEliotLogs(),
        ])



class TestCase(TesttoolsTestCase):
    """
    A base class for test cases which automatically uses the
    ``CaptureEliotLogs`` fixture.
    """
    # expectThat and Hypothesis don't communicate well about when the
    # test has failed.  Give them a little help.  These two Hypothesis
    # hooks will check for a flag that testtools sets when it thinks
    # the test has failed and turn it into something Hypothesis can
    # recognize.
    def setup_example(self):
        try:
            # TesttoolsTestCase starts without this attribute set at all.  Get
            # us back to that state.  It won't be set at all on the first
            # setup_example call, nor if the previous run didn't have a failed
            # expectation.
            del self.force_failure
        except AttributeError:
            pass

    def teardown_example(self, ignored):
        if getattr(self, "force_failure", False):
            # If testtools things it's time to stop, translate this into a
            # test failure exception that Hypothesis can see.  This lets
            # Hypothesis know when it has found a falsifying example.  Without
            # it, Hypothesis can't see which of its example runs caused
            # problems.
            self.fail("expectation failed")



def assertNoResult(case, d):
    """
    Assert that ``d`` does not have a result at this point.
    """
    result = []
    d.addBoth(result.append)
    if result:
        if isinstance(result[0], Failure):
            result[0].raiseException()
        else:
            case.fail("Got {} but expected no result".format(result[0]))
