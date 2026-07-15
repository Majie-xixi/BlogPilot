from pathlib import Path
import tempfile
import unittest

from blogpost.article_store import ArticleStore
from blogpost.config import AppConfig
from blogpost.corpus import CorpusIndexer
from blogpost.db import Database
from blogpost.domain import Article, PublishResult, QualityIssue, QualityReport, RunStatus, Trigger
from blogpost.llm.generation import Topic
from blogpost.pipeline import PublishingPipeline
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
