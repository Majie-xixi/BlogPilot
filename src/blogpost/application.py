from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import sys
from collections.abc import Callable, Iterable

from blogpost.article_store import ArticleStore
from blogpost.browser.chrome import ChromeController, find_supported_browser
from blogpost.config import AppConfig
from blogpost.corpus import CorpusIndexer
from blogpost.db import Database
from blogpost.domain import Account, Article, DEFAULT_ACCOUNT_ID, PublishResult, RunStatus, Trigger
from blogpost.llm.client import OpenAICompatibleClient
from blogpost.llm.generation import ArticleGenerator, ArticleRewriter, TopicPlanner
from blogpost.llm.review import ModelReviewer
from blogpost.paths import app_data_dir, browser_profile_dir, config_path, database_path
from blogpost.pipeline import PublishingPipeline
from blogpost.publishers.cto51 import Cto51Publisher
from blogpost.quality import QualityGate
from blogpost.repositories import Repository
from blogpost.run_lock import RunLock
from blogpost.scheduler import WindowsTaskScheduler
from blogpost.secrets import DpapiSecretStore
from blogpost.markdown import parse_markdown
from blogpost.network import is_metered_connection


AccountProgress = Callable[[Account, RunStatus, str], None]


@dataclass(slots=True)
class ApplicationContext:
    config: AppConfig
    repository: Repository
    secrets: DpapiSecretStore
    chrome: ChromeController
    publisher: Cto51Publisher
    scheduler: WindowsTaskScheduler

    def accounts(self, *, enabled_only: bool = False) -> list[Account]:
        return self.repository.list_accounts(enabled_only=enabled_only)

    def account(self, account_id: str = DEFAULT_ACCOUNT_ID) -> Account:
        return self.repository.get_account(account_id)

    def config_for_account(self, account_id: str = DEFAULT_ACCOUNT_ID) -> AppConfig:
        account = self.account(account_id)
        return replace(
            self.config,
            generated_dir=self.config.generated_dir / account.article_subdir,
            schedule_time=account.schedule_time,
            category=account.category,
            profile_url=account.profile_url,
        )

    def publisher_for_account(self, account_id: str = DEFAULT_ACCOUNT_ID) -> Cto51Publisher:
        account = self.account(account_id)
        if account_id == DEFAULT_ACCOUNT_ID:
            self.publisher.expected_profile_url = account.profile_url
            self.publisher.secondary_category = account.secondary_category
            self.publisher.personal_category = account.personal_category
            return self.publisher
        browser = find_supported_browser()
        chrome = ChromeController(
            browser.executable,
            browser_profile_dir(account_id, browser.name),
            default_port=9229 + max(0, account.sort_order),
            browser_name=browser.name,
        )
        return Cto51Publisher(
            chrome,
            app_data_dir() / "diagnostics" / account_id,
            account.profile_url,
            account.secondary_category,
            account.personal_category,
        )

    def build_pipeline(self, account_id: str = DEFAULT_ACCOUNT_ID) -> PublishingPipeline:
        api_key = self.secrets.get_api_key()
        if not api_key:
            raise ValueError("请先在设置中填写大模型 API Key")
        account = self.account(account_id)
        if not account.enabled:
            raise ValueError(f"账号“{account.display_name}”已停用")
        config = self.config_for_account(account_id)
        client = OpenAICompatibleClient(
            config.api_base_url,
            config.model,
            api_key,
        )
        return PublishingPipeline(
            config,
            self.repository,
            CorpusIndexer(config.history_dir, self.config.generated_dir),
            TopicPlanner(
                client,
                account.article_type,
                account.content_directions,
                account.keywords,
            ),
            ArticleGenerator(client),
            QualityGate(
                config.min_chinese_chars,
                config.title_similarity_threshold,
                config.content_similarity_threshold,
            ),
            ModelReviewer(client),
            ArticleRewriter(client),
            ArticleStore(config.generated_dir),
            self.publisher_for_account(account_id),
            RunLock(app_data_dir() / "run.lock"),
            account_id,
        )

    def run_accounts(
        self,
        account_ids: Iterable[str] | None,
        trigger: Trigger,
        *,
        allow_same_day: bool = False,
        due_only: bool = False,
        progress: AccountProgress | None = None,
    ) -> list[tuple[Account, PublishResult]]:
        selected = set(account_ids or [])
        now = datetime.now()
        accounts = [
            account
            for account in self.accounts(enabled_only=True)
            if (not selected or account.id in selected)
            and (not due_only or account.schedule_time <= now.time())
        ]
        callback = progress or (lambda account, status, message: None)
        if trigger == Trigger.SCHEDULED and is_metered_connection():
            message = "检测到按流量计费网络，自动生成和发布已暂停"
            results = []
            for account in accounts:
                run = self.repository.create_run(trigger, account.id)
                self.repository.update_run(run.id, RunStatus.SKIPPED, error_summary=message)
                result = PublishResult(RunStatus.SKIPPED, message=message)
                callback(account, result.status, message)
                results.append((account, result))
            return results

        results: list[tuple[Account, PublishResult]] = []
        for account in accounts:
            callback(account, RunStatus.QUEUED, f"开始处理账号：{account.display_name}")
            try:
                pipeline = self.build_pipeline(account.id)
                result = pipeline.run(
                    trigger,
                    allow_same_day=allow_same_day,
                    progress=lambda status, message, current=account: callback(
                        current, status, message
                    ),
                )
            except Exception as exc:
                result = PublishResult(RunStatus.FAILED, message=str(exc))
                callback(account, result.status, str(exc))
            results.append((account, result))
        return results

    def retry_saved_article(
        self,
        account_id: str,
        path: Path,
        *,
        progress: Callable[[RunStatus, str], None] | None = None,
    ) -> PublishResult:
        callback = progress or (lambda status, message: None)
        record = self.repository.article_by_path(str(path), account_id)
        if record is None:
            raise ValueError("这篇文章不属于当前账号，已停止重发")
        payload = path.read_text(encoding="utf-8")
        expected = str(record["sha256"])
        actual = sha256((payload.rstrip() + "\n").encode("utf-8")).hexdigest()
        if actual != expected:
            raise ValueError("文章文件内容已改变，请先人工确认后再处理")
        document = parse_markdown(payload)
        if not document.title or document.chinese_chars < self.config.min_chinese_chars:
            raise ValueError("已保存文章未通过标题或最低字数检查")
        account = self.account(account_id)
        config = self.config_for_account(account_id)
        run = None
        try:
            with RunLock(app_data_dir() / "run.lock"):
                run = self.repository.create_publish_retry(str(path), account_id=account_id)
                callback(RunStatus.PUBLISHING, "正在重发已保存文章，不调用大模型")
                result = self.publisher_for_account(account_id).publish(
                    Article(document.title, payload, str(record["topic"])),
                    account.category,
                    config.dry_run,
                )
                if result.status in {RunStatus.PUBLISHED, RunStatus.UNKNOWN, RunStatus.FAILED}:
                    self.repository.update_run(
                        run.id,
                        result.status,
                        error_code=None if result.status == RunStatus.PUBLISHED else "publish_failed",
                        error_summary=result.message,
                    )
                else:
                    self.repository.force_run_status(run.id, result.status)
                callback(result.status, result.message or result.url or result.status.value)
                return PublishResult(
                    result.status,
                    result.url,
                    result.message,
                    str(path),
                )
        except Exception:
            if run is not None:
                self.repository.force_run_status(run.id, RunStatus.FAILED)
            raise


def scheduler_for_runtime() -> WindowsTaskScheduler:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        return WindowsTaskScheduler(executable, executable.parent, "run-daily")

    project_root = Path(__file__).resolve().parents[2]
    return WindowsTaskScheduler(
        Path(sys.executable),
        project_root,
        f'"{project_root / "main.py"}" run-daily',
    )


def build_context() -> ApplicationContext:
    config = AppConfig.load(config_path())
    database = Database(database_path())
    database.initialize()
    repository = Repository(database)
    default_account = repository.update_default_account_from_legacy(
        profile_url=config.profile_url,
        category=config.category,
        schedule_time=config.schedule_time,
    )
    secrets = DpapiSecretStore(app_data_dir() / "api-key.bin")
    browser = find_supported_browser()
    chrome = ChromeController(
        browser.executable,
        browser_profile_dir(browser_name=browser.name),
        browser_name=browser.name,
    )
    publisher = Cto51Publisher(
        chrome,
        app_data_dir() / "diagnostics" / DEFAULT_ACCOUNT_ID,
        default_account.profile_url,
        default_account.secondary_category,
        default_account.personal_category,
    )
    scheduler = scheduler_for_runtime()
    return ApplicationContext(config, repository, secrets, chrome, publisher, scheduler)
