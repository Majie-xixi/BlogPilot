from datetime import datetime
import unittest

from blogpost.domain import Run, RunStatus, Trigger, InvalidTransition


class DomainTests(unittest.TestCase):
    def test_run_moves_through_success_path(self):
        run = Run.new(Trigger.MANUAL)
        for state in (
            RunStatus.PLANNING,
            RunStatus.GENERATING,
            RunStatus.VALIDATING,
            RunStatus.SAVING,
            RunStatus.PUBLISHING,
            RunStatus.PUBLISHED,
        ):
            run.transition(state)
        self.assertEqual(run.status, RunStatus.PUBLISHED)
        self.assertIsInstance(run.finished_at, datetime)

    def test_terminal_state_cannot_transition(self):
        run = Run.new(Trigger.SCHEDULED)
        run.transition(RunStatus.SKIPPED)
        with self.assertRaises(InvalidTransition):
            run.transition(RunStatus.PLANNING)
