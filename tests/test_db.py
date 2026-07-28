from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest

from blogpost.db import Database
from blogpost.domain import RunStatus, Trigger
from blogpost.repositories import Repository


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "test.db")
        self.db.initialize()
        self.repo = Repository(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_initialize_is_idempotent_and_run_is_persisted(self):
        self.db.initialize()
        run = self.repo.create_run(Trigger.MANUAL)
        self.repo.update_run(run.id, RunStatus.PLANNING)
        loaded = self.repo.get_run(run.id)
        self.assertEqual(loaded.status, RunStatus.PLANNING)

    def test_successful_publication_is_found_by_local_date(self):
        run = self.repo.create_run(Trigger.SCHEDULED)
        self.repo.force_run_status(run.id, RunStatus.PUBLISHED)
        self.assertTrue(self.repo.has_successful_publication(date.today()))
        self.assertEqual(self.repo.count_successful_days(date.today().year, date.today().month), 1)

    def test_profile_month_count_cache_round_trip(self):
        checked_at = datetime(2026, 7, 28, 10, 0)
        profile_url = "https://blog.51cto.com/u_987654"

        self.repo.save_profile_month_count(
            "default",
            profile_url,
            checked_at,
            18,
        )

        self.assertEqual(
            self.repo.cached_profile_month_count(
                "default",
                profile_url,
                2026,
                7,
            ),
            (18, checked_at),
        )
        self.assertIsNone(
            self.repo.cached_profile_month_count(
                "other",
                profile_url,
                2026,
                7,
            )
        )
        self.assertIsNone(
            self.repo.cached_profile_month_count(
                "default",
                "https://blog.51cto.com/u_111111",
                2026,
                7,
            )
        )
