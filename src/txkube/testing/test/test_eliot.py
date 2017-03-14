# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube.testing._eliot``.
"""

from eliot import start_action, add_destination, remove_destination

from testtools.matchers import Contains

from .. import TestCase

from .._eliot import _eliottree


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
        add_destination(events.append)
        self.addCleanup(lambda: remove_destination(events.append))

        with start_action(action_type=u"foo"):
            pass

        # I don't know exactly what the tree rendering looks like.  That's why
        # I'm using eliot-tree!  So this assertion is sort of lame.
        self.assertThat(
            _eliottree(events).decode("utf-8"),
            Contains(u"foo@1/started"),
        )
