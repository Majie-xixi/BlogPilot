from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blogpost.article_store import ArticleStore
from blogpost.config import AppConfig
from blogpost.corpus import CorpusIndexer
from blogpost.db import Database
from blogpost.domain import Article, PublishResult, QualityIssue, QualityReport, RunStatus, Trigger
from blogpost.llm.generation import Topic
from blogpost.pipeline import PublishingPipeline
from blogpost.publishers.cto51 import Cto51Publisher
from blogpost.repositories import Repository
from blogpost.run_lock import RunLock


class FakePlanner:
    def choose(self, corpus, title_threshold, content_threshold):
        return Topic("AIOps 日志聚类的工程边界", "日志聚类与规则协作", "AIOps")


class FakeGenerator:
    def generate(self, title, summary, style_summary):
        return Article(title, f"# {title}\n\n" + ("人工智能运维通过日志聚类识别异常模式。" * 120), title)


class PassingGate:
    def check(self, markdown, corpus):
        return QualityReport(True, (), 100)


class PassingReviewer:
    def review(self, markdown):
        return QualityReport(True, (), 90)


class FailingGate:
    def check(self, markdown, corpus):
        return QualityReport(
            False,
            (QualityIssue("quality", "需要补充技术细节"),),
            60,
        )


class FakeRewriter:
    def rewrite(self, markdown, feedback):
        return markdown


class FakePublisher:
    def __init__(self):
        self.calls = 0

    def publish(self, article, category, dry_run):
        self.calls += 1
        return PublishResult(RunStatus.PUBLISHED, "https://blog.51cto.com/u/test/1")


class PipelineTests(unittest.TestCase):
    def test_cancel_during_planning_stops_before_generation_and_publish(self):
        from blogpost.pipeline import Cancellation
        cancellation = Cancellation()
        original = self.pipeline.planner.choose
        def choose(*args):
            result = original(*args)
            self.assertTrue(cancellation.cancel())
            return result
        self.pipeline.planner.choose = choose
        result = self.pipeline.run(Trigger.MANUAL, cancellation=cancellation)
        self.assertEqual(result.status, RunStatus.SKIPPED)
        self.assertIn('取消', result.message)
        self.assertEqual(self.publisher.calls, 0)
        self.assertFalse(list(self.cfg.generated_dir.glob('*.md')))

    def test_cannot_claim_cancel_during_publish(self):
        from blogpost.pipeline import Cancellation
        cancellation = Cancellation()
        def publish(*args):
            self.assertFalse(cancellation.cancel())
            return PublishResult(RunStatus.PUBLISHED)
        self.publisher.publish = publish
        result = self.pipeline.run(Trigger.MANUAL, cancellation=cancellation)
        self.assertEqual(result.status, RunStatus.PUBLISHED)

    def test_cancel_after_save_preserves_article_and_never_publishes(self):
        from blogpost.pipeline import Cancellation
        cancellation = Cancellation()
        original = self.pipeline.article_store.save
        def save(*args):
            stored = original(*args)
            self.assertTrue(cancellation.cancel())
            return stored
        self.pipeline.article_store.save = save
        result = self.pipeline.run(Trigger.MANUAL, cancellation=cancellation)
        self.assertEqual(result.status, RunStatus.SKIPPED)
        self.assertEqual(self.publisher.calls, 0)
        self.assertEqual(len(list(self.cfg.generated_dir.glob('*.md'))), 1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        history = root / "history"
        history.mkdir()
        self.cfg = AppConfig(
            history_dir=history,
            generated_dir=history / "generated_posts",
            dry_run=False,
        )
        self.database = Database(root / "app.db")
        self.database.initialize()
        self.repo = Repository(self.database)
        self.publisher = FakePublisher()
        self.pipeline = PublishingPipeline(
            self.cfg,
            self.repo,
            CorpusIndexer(self.cfg.history_dir, self.cfg.generated_dir),
            FakePlanner(),
            FakeGenerator(),
            PassingGate(),
            PassingReviewer(),
            FakeRewriter(),
            ArticleStore(self.cfg.generated_dir),
            self.publisher,
            RunLock(root / "run.lock"),
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_successful_pipeline_persists_and_publishes(self):
        result = self.pipeline.run(Trigger.MANUAL)
        self.assertEqual(result.status, RunStatus.PUBLISHED)
        self.assertTrue(Path(result.article_path).exists())
        self.assertEqual(self.publisher.calls, 1)
        self.assertEqual(len(list(self.cfg.generated_dir.glob("*.md"))), 1)

    def test_failed_quality_still_saves_review_draft(self):
        self.pipeline.quality_gate = FailingGate()

        result = self.pipeline.run(Trigger.MANUAL)

        self.assertEqual(result.status, RunStatus.NEEDS_REVIEW)
        self.assertIn("需要补充技术细节", result.message)
        self.assertTrue(Path(result.article_path).exists())
        self.assertIn("待检查", Path(result.article_path).name)
        self.assertEqual(self.repo.latest_article_path(), result.article_path)
        self.assertEqual(self.publisher.calls, 0)

    def test_pipeline_emits_stage_logs(self):
        with self.assertLogs("blogpost.pipeline", level="INFO") as captured:
            self.pipeline.run(Trigger.MANUAL)

        output = "\n".join(captured.output)
        self.assertIn("status=planning", output)
        self.assertIn("status=generating", output)
        self.assertIn("status=publishing", output)

    def test_scheduled_run_skips_after_today_success(self):
        self.pipeline.run(Trigger.MANUAL)
        result = self.pipeline.run(Trigger.SCHEDULED)
        self.assertEqual(result.status, RunStatus.SKIPPED)
        self.assertEqual(self.publisher.calls, 1)

    def test_unknown_online_status_stops_before_generation_and_finishes_run(self):
        self.publisher.expected_profile_url = "https://blog.51cto.com/u_123456"
        self.publisher.has_publication_on = lambda day: None
        events = []
        with (
            patch.object(
                self.pipeline.planner,
                "choose",
                side_effect=AssertionError("must not plan with unknown online status"),
            ),
            patch.object(
                self.pipeline.generator,
                "generate",
                side_effect=AssertionError("must not generate with unknown online status"),
            ),
        ):
            result = self.pipeline.run(
                Trigger.MANUAL,
                progress=lambda status, message: events.append((status, message)),
            )

        self.assertEqual(result.status, RunStatus.UNKNOWN)
        self.assertIn("无法核对 51CTO 今日发布状态", result.message)
        run = next(iter(self.repo.recent_runs(1)))
        self.assertEqual(run.status, RunStatus.UNKNOWN)
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(run.error_code, "online_status_unknown")
        self.assertEqual(run.error_summary, result.message)
        self.assertEqual(events, [(RunStatus.UNKNOWN, result.message)])
        self.assertEqual(self.publisher.calls, 0)
        self.assertEqual(list(self.cfg.generated_dir.glob("*.md")), [])
        self.assertFalse(self.pipeline.run_lock.path.exists())

    def test_explicit_empty_profile_allows_first_article(self):
        html = (Path(__file__).parent / "fixtures" / "cto51_empty_profile.html").read_text(
            encoding="utf-8"
        )
        publisher = Cto51Publisher(
            None, Path(self.temp.name) / "diagnostics", "https://blog.51cto.com/u_987654"
        )
        self.pipeline.publisher = publisher
        with (
            patch("blogpost.publishers.cto51_profile._download_profile_html", return_value=html),
            patch.object(Cto51Publisher, "publish", return_value=PublishResult(RunStatus.PUBLISHED)),
        ):
            result = self.pipeline.run(Trigger.MANUAL)

        self.assertEqual(result.status, RunStatus.PUBLISHED)
        self.assertTrue(Path(result.article_path).exists())
        run = next(iter(self.repo.recent_runs(1)))
        self.assertEqual(run.status, RunStatus.PUBLISHED)
        self.assertIsNotNone(run.finished_at)
