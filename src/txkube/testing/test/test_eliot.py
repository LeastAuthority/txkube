# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube.testing._eliot``.
"""

from eliot import start_action, add_destinations, remove_destination

from testtools.matchers import (
    Contains,
    Equals,
)

from .. import TestCase

from .._eliot import (
    CaptureEliotLogs,
    _eliottree,
)


class EliotTreeTests(TestCase):
    """
    Tests for ``txkube.testing._eliot._eliottree``.
    """
    def test_tree(self):
        """
        ``_eliottree`` returns a ``bytes`` string containing a rendered tree of
        Eliot actions and messages.
        """
        events = []
        add_destinations(events.append)
        self.addCleanup(lambda: remove_destination(events.append))

        with start_action(action_type=u"foo"):
            pass

        # I don't know exactly what the tree rendering looks like.  That's why
        # I'm using eliot-tree!  So this assertion is sort of lame.
        self.assertThat(
            _eliottree(events),
            Contains(u"foo/1 \N{RIGHTWARDS DOUBLE ARROW} started"),
        )



class CaptureEliotLogsTests(TestCase):
    """
    Tests for ``txkube.testing._eliot.CaptureEliotLogs``.
    """
    def test_logs_as_detail(self):
        """
        Captured logs are available as details on the fixture.
        """
        fixture = CaptureEliotLogs()
        fixture.setUp()
        try:
            with start_action(action_type=u"foo"):
                pass
            details = fixture.getDetails()
        finally:
            fixture.cleanUp()
        self.assertThat(
            details[fixture.LOG_DETAIL_NAME].as_text(),
            Equals(_eliottree(fixture.logs)),
        )
