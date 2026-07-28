from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blogpost.application import ApplicationContext
from blogpost.db import Database
from blogpost.domain import RunStatus, Trigger
from blogpost.repositories import Repository


class ApplicationNetworkTests(unittest.TestCase):
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
