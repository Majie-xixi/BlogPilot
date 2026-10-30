from __future__ import annotations

from collections.abc import Callable
from datetime import date
import json
import logging
import threading

from blogpost.article_store import ArticleStore
from blogpost.config import AppConfig
from blogpost.corpus import CorpusIndexer
from blogpost.domain import (
    Article,
    DEFAULT_ACCOUNT_ID,
    PublishResult,
    QualityReport,
    RunStatus,
    Trigger,
)
from blogpost.markdown import normalize_single_h1, parse_markdown
from blogpost.logging_setup import redact
from blogpost.repositories import Repository
from blogpost.run_lock import AlreadyRunning, RunLock
from blogpost.style import summarize_style


logger = logging.getLogger(__name__)
Progress = Callable[[RunStatus, str], None]


class Cancelled(Exception):
    pass


class Cancellation:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled = False
        self._publishing = False

    def cancel(self) -> bool:
        with self._lock:
            if self._publishing:
                return False
            self._cancelled = True
            return True

    def check(self) -> None:
        with self._lock:
            if self._cancelled:
                raise Cancelled()

    def begin_publish(self) -> None:
        with self._lock:
            if self._cancelled:
                raise Cancelled()
            self._publishing = True

    def end_publish(self) -> None:
        with self._lock:
            self._publishing = False


class PublishingPipeline:
    def __init__(
        self,
        config: AppConfig,
        repository: Repository,
        corpus_indexer: CorpusIndexer,
        planner: object,
        generator: object,
        quality_gate: object,
        reviewer: object,
        rewriter: object,
        article_store: ArticleStore,
        publisher: object,
        run_lock: RunLock,
        account_id: str = DEFAULT_ACCOUNT_ID,
    ):
        self.config = config
        self.repository = repository
        self.corpus_indexer = corpus_indexer
        self.planner = planner
        self.generator = generator
        self.quality_gate = quality_gate
        self.reviewer = reviewer
        self.rewriter = rewriter
        self.article_store = article_store
        self.publisher = publisher
        self.run_lock = run_lock
        self.account_id = account_id

    def run(
        self,
        trigger: Trigger,
        *,
        allow_same_day: bool = False,
        progress: Progress | None = None,
        cancellation: Cancellation | None = None,
    ) -> PublishResult:
        self.config.validate_for_run()
        callback = progress or (lambda status, message: None)
        cancellation = cancellation or Cancellation()

        def emit(status: RunStatus, message: str) -> None:
            logger.info(
                "pipeline status=%s account_id=%s message=%s",
                status.value,
                self.account_id,
                message,
            )
            callback(status, message)

        try:
            with self.run_lock:
                run = self.repository.create_run(trigger, self.account_id)
                logger.info(
                    "pipeline started run_id=%s trigger=%s account_id=%s",
                    run.id,
                    trigger.value,
                    self.account_id,
                )
                local_published = self.repository.has_successful_publication(
                    date.today(),
                    self.account_id,
                )
                online_check = getattr(self.publisher, "has_publication_on", None)
                online_published = online_check(date.today()) if callable(online_check) and not local_published else False
                profile_url = str(getattr(self.publisher, "expected_profile_url", "")).strip()
                if online_published is None and profile_url and not allow_same_day:
                    message = "无法核对 51CTO 今日发布状态，为防止重复发文，本次已停止且不会调用大模型"
                    self.repository.update_run(
                        run.id,
                        RunStatus.UNKNOWN,
                        error_code="online_status_unknown",
                        error_summary=message,
                    )
                    emit(RunStatus.UNKNOWN, message)
                    return PublishResult(RunStatus.UNKNOWN, message=message)
                if (local_published or online_published is True) and not allow_same_day:
                    source = "51CTO 线上" if online_published is True else "软件记录"
                    message = f"{source}显示今天已经发布，已跳过且不会调用大模型"
                    self.repository.update_run(run.id, RunStatus.SKIPPED, error_summary=message)
                    emit(RunStatus.SKIPPED, message)
                    return PublishResult(RunStatus.SKIPPED, message=message)
                try:
                    cancellation.check()
                    corpus = self.corpus_indexer.scan_history() + self.corpus_indexer.scan_generated()
                    self.repository.update_run(run.id, RunStatus.PLANNING)
                    emit(RunStatus.PLANNING, "正在选择未重复的 AI 技术主题")
                    topic = self.planner.choose(
                        corpus,
                        self.config.title_similarity_threshold,
                        self.config.content_similarity_threshold,
                    )
                    cancellation.check()

                    self.repository.update_run(run.id, RunStatus.GENERATING)
                    emit(RunStatus.GENERATING, f"正在生成：{topic.title}")
                    article = self.generator.generate(
                        topic.title,
                        topic.summary,
                        summarize_style(corpus),
                    )
                    cancellation.check()

                    self.repository.update_run(run.id, RunStatus.VALIDATING)
                    emit(RunStatus.VALIDATING, "正在执行原创性与质量检查")
                    deterministic = self.quality_gate.check(article.markdown, corpus)
                    model_report = self.reviewer.review(article.markdown) if deterministic.passed else deterministic
                    cancellation.check()
                    if not deterministic.passed or not model_report.passed:
                        feedback = self._feedback(deterministic, model_report)
                        emit(RunStatus.VALIDATING, f"首次检查未通过，正在按反馈重写：{feedback}")
                        rewritten = normalize_single_h1(
                            self.rewriter.rewrite(article.markdown, feedback),
                            topic.title,
                        )
                        parsed = parse_markdown(rewritten)
                        article = Article(parsed.title, rewritten, topic.title)
                        deterministic = self.quality_gate.check(article.markdown, corpus)
                        model_report = self.reviewer.review(article.markdown) if deterministic.passed else deterministic
                        cancellation.check()
                    if not deterministic.passed or not model_report.passed:
                        feedback = self._feedback(deterministic, model_report)
                        self.repository.update_run(run.id, RunStatus.SAVING)
                        emit(RunStatus.SAVING, "质量检查未通过，正在保存待检查草稿")
                        stored = self.article_store.save(f"{article.title}-待检查", article.markdown)
                        document = parse_markdown(article.markdown)
                        article_id = self.repository.add_article(
                            article.title,
                            str(stored.path),
                            stored.sha256,
                            document.chinese_chars,
                            topic.title,
                            json.dumps(
                                {
                                    "passed": False,
                                    "deterministic": deterministic.score,
                                    "review": model_report.score,
                                    "issues": [
                                        issue.message
                                        for report in (deterministic, model_report)
                                        for issue in report.issues
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                            account_id=self.account_id,
                        )
                        self.repository.update_run(
                            run.id,
                            RunStatus.NEEDS_REVIEW,
                            article_id=article_id,
                            error_code="quality_failed",
                            error_summary=feedback,
                        )
                        message = f"{feedback}；待检查草稿已保存到 {stored.path}"
                        emit(RunStatus.NEEDS_REVIEW, message)
                        return PublishResult(
                            RunStatus.NEEDS_REVIEW,
                            message=message,
                            article_path=str(stored.path),
                        )

                    self.repository.update_run(run.id, RunStatus.SAVING)
                    emit(RunStatus.SAVING, "正在保存 Markdown")
                    stored = self.article_store.save(article.title, article.markdown)
                    document = parse_markdown(article.markdown)
                    article_id = self.repository.add_article(
                        article.title,
                        str(stored.path),
                        stored.sha256,
                        document.chinese_chars,
                        topic.title,
                        json.dumps(
                            {"deterministic": deterministic.score, "review": model_report.score},
                            ensure_ascii=False,
                        ),
                        account_id=self.account_id,
                    )

                    cancellation.begin_publish()
                    try:
                        self.repository.update_run(run.id, RunStatus.PUBLISHING, article_id=article_id)
                        emit(RunStatus.PUBLISHING, "正在填充 51CTO 编辑器")
                        result = self.publisher.publish(article, self.config.category, self.config.dry_run)
                        if result.status in {RunStatus.PUBLISHED, RunStatus.UNKNOWN, RunStatus.FAILED}:
                            self.repository.update_run(
                                run.id,
                                result.status,
                                article_id=article_id,
                                error_code=None if result.status == RunStatus.PUBLISHED else "publish_failed",
                                error_summary=result.message,
                            )
                        else:
                            self.repository.force_run_status(run.id, result.status)
                        emit(result.status, result.message or result.url or result.status.value)
                        return PublishResult(
                            result.status,
                            url=result.url,
                            message=result.message,
                            article_path=str(stored.path),
                        )
                    finally:
                        cancellation.end_publish()
                except Cancelled:
                    self.repository.force_run_status(run.id, RunStatus.SKIPPED)
                    message = "已取消，未进入发布步骤；已保存的文章会保留"
                    emit(RunStatus.SKIPPED, message)
                    return PublishResult(RunStatus.SKIPPED, message=message)
                except Exception as exc:
                    detail = redact(str(exc))
                    logger.error("pipeline failed run_id=%s error_type=%s message=%s", run.id, type(exc).__name__, detail)
                    self.repository.force_run_status(run.id, RunStatus.FAILED)
                    emit(RunStatus.FAILED, detail)
                    return PublishResult(RunStatus.FAILED, message=detail)
        except AlreadyRunning as exc:
            return PublishResult(RunStatus.SKIPPED, message=str(exc))

    @staticmethod
    def _feedback(*reports: QualityReport) -> str:
        messages = []
        for report in reports:
            messages.extend(issue.message for issue in report.issues)
        return "；".join(dict.fromkeys(messages)) or "模型复核未通过"
