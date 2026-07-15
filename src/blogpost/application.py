from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

from blogpost.article_store import ArticleStore
from blogpost.browser.chrome import ChromeController, find_chrome
from blogpost.config import AppConfig
from blogpost.corpus import CorpusIndexer
from blogpost.db import Database
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


@dataclass(slots=True)
class ApplicationContext:
    config: AppConfig
    repository: Repository
    secrets: DpapiSecretStore
    chrome: ChromeController
    publisher: Cto51Publisher
    scheduler: WindowsTaskScheduler

    def build_pipeline(self) -> PublishingPipeline:
        api_key = self.secrets.get_api_key()
        if not api_key:
            raise ValueError("请先在设置中填写大模型 API Key")
        client = OpenAICompatibleClient(
            self.config.api_base_url,
            self.config.model,
            api_key,
        )
        return PublishingPipeline(
            self.config,
            self.repository,
            CorpusIndexer(self.config.history_dir, self.config.generated_dir),
            TopicPlanner(client),
            ArticleGenerator(client),
            QualityGate(
                self.config.min_chinese_chars,
                self.config.title_similarity_threshold,
                self.config.content_similarity_threshold,
            ),
            ModelReviewer(client),
            ArticleRewriter(client),
            ArticleStore(self.config.generated_dir),
            self.publisher,
            RunLock(app_data_dir() / "run.lock"),
        )


def build_context() -> ApplicationContext:
    config = AppConfig.load(config_path())
    database = Database(database_path())
    database.initialize()
    repository = Repository(database)
    secrets = DpapiSecretStore(app_data_dir() / "api-key.bin")
    chrome = ChromeController(find_chrome(), browser_profile_dir())
    publisher = Cto51Publisher(chrome, app_data_dir() / "diagnostics")
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        arguments = "run-daily"
        working_dir = executable.parent
    else:
        executable = Path(sys.executable)
        arguments = "-m blogpost run-daily"
        working_dir = Path.cwd()
    scheduler = WindowsTaskScheduler(executable, working_dir, arguments)
    return ApplicationContext(config, repository, secrets, chrome, publisher, scheduler)
