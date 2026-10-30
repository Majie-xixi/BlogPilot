from pathlib import Path
from datetime import time
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

from blogpost.application import ApplicationContext
from blogpost.db import Database
from blogpost.domain import RunStatus, Trigger
from blogpost.repositories import Repository


class ApplicationNetworkTests(unittest.TestCase):
    def test_batch_cancellation_skips_remaining_accounts(self):
        from blogpost.pipeline import Cancellation
        from blogpost.domain import PublishResult
        first = SimpleNamespace(id='first', display_name='first', schedule_time=time(0, 0))
        second = SimpleNamespace(id='second', display_name='second', schedule_time=time(0, 0))
        token = Cancellation()
        pipeline = Mock()
        def run(*args, **kwargs):
            token.cancel()
            return PublishResult(RunStatus.SKIPPED, message='已取消')
        pipeline.run.side_effect = run
        context = Mock()
        context.accounts.return_value = [first, second]
        context.build_pipeline.return_value = pipeline
        with patch('blogpost.application.internet_connection_status', return_value=True):
            results = ApplicationContext.run_accounts(context, None, Trigger.MANUAL, cancellation=token)
        self.assertEqual([result.status for _, result in results], [RunStatus.SKIPPED, RunStatus.SKIPPED])
        context.build_pipeline.assert_called_once_with('first')

    def test_offline_run_stops_before_pipeline_is_built(self):
        with tempfile.TemporaryDirectory() as root:
            database = Database(Path(root) / "test.db")
            database.initialize()
            repository = Repository(database)
            context = ApplicationContext(
                config=None,
                repository=repository,
                secrets=None,
                chrome=None,
                publisher=None,
                scheduler=None,
            )
            with (
                patch(
                    "blogpost.application.internet_connection_status",
                    return_value=False,
                ),
                patch.object(
                    ApplicationContext,
                    "build_pipeline",
                    side_effect=AssertionError("pipeline must not be built"),
                ),
            ):
                results = context.run_accounts(None, Trigger.MANUAL)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1].status, RunStatus.FAILED)
        self.assertIn("网络不可用", results[0][1].message)


if __name__ == "__main__":
    unittest.main()
