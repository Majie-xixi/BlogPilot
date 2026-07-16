from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import StrEnum
import uuid


class Trigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    SYNCED = "synced"


class RunStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    GENERATING = "generating"
    VALIDATING = "validating"
    SAVING = "saving"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    SKIPPED = "skipped"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    UNKNOWN = "unknown"


TERMINAL_STATES = {
    RunStatus.PUBLISHED,
    RunStatus.SKIPPED,
    RunStatus.NEEDS_REVIEW,
    RunStatus.FAILED,
    RunStatus.UNKNOWN,
}

_NEXT: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.PLANNING, RunStatus.SKIPPED, RunStatus.FAILED},
    RunStatus.PLANNING: {RunStatus.GENERATING, RunStatus.FAILED},
    RunStatus.GENERATING: {RunStatus.VALIDATING, RunStatus.FAILED},
    RunStatus.VALIDATING: {
        RunStatus.SAVING,
        RunStatus.NEEDS_REVIEW,
        RunStatus.FAILED,
    },
    RunStatus.SAVING: {RunStatus.PUBLISHING, RunStatus.NEEDS_REVIEW, RunStatus.FAILED},
    RunStatus.PUBLISHING: {
        RunStatus.PUBLISHED,
        RunStatus.UNKNOWN,
        RunStatus.FAILED,
    },
}


class InvalidTransition(RuntimeError):
    pass


DEFAULT_ACCOUNT_ID = "default"


@dataclass(slots=True, frozen=True)
class Account:
    id: str
    display_name: str
    profile_url: str = ""
    enabled: bool = True
    sort_order: int = 0
    schedule_time: time = time(10, 0)
    monthly_target: int = 21
    category: str = "AI 智能体"
    secondary_category: str = "编程 Agent"
    personal_category: str = "AI"
    article_type: str = "技术解析"
    content_directions: str = "AI Agent、AI 编程、Prompt、AIOps、边缘 AI、大模型工程"
    keywords: str = ""
    article_subdir: str = "default"

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("账号 ID 不能为空")
        if not self.display_name.strip():
            raise ValueError("账号名称不能为空")
        if self.profile_url and not self.profile_url.startswith("https://blog.51cto.com/u_"):
            raise ValueError("51CTO 主页地址格式不正确")
        if not 1 <= self.monthly_target <= 100:
            raise ValueError("每月目标篇数必须在 1 到 100 之间")
        if not self.article_type.strip():
            raise ValueError("博文类型不能为空")
        if not self.article_subdir.strip() or any(char in self.article_subdir for char in '<>:"/\\|?*'):
            raise ValueError("文章子目录名称无效")


@dataclass(slots=True)
class Run:
    id: str
    trigger: Trigger
    status: RunStatus = RunStatus.QUEUED
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    article_id: int | None = None
    error_code: str | None = None
    error_summary: str | None = None
    account_id: str = DEFAULT_ACCOUNT_ID

    @classmethod
    def new(cls, trigger: Trigger, account_id: str = DEFAULT_ACCOUNT_ID) -> "Run":
        return cls(id=str(uuid.uuid4()), trigger=trigger, account_id=account_id)

    def transition(self, target: RunStatus) -> None:
        if target not in _NEXT.get(self.status, set()):
            raise InvalidTransition(f"cannot transition {self.status} to {target}")
        self.status = target
        if target in TERMINAL_STATES:
            self.finished_at = datetime.now()


@dataclass(slots=True, frozen=True)
class Article:
    title: str
    markdown: str
    topic: str


@dataclass(slots=True, frozen=True)
class QualityIssue:
    code: str
    message: str
    hard: bool = True


@dataclass(slots=True, frozen=True)
class QualityReport:
    passed: bool
    issues: tuple[QualityIssue, ...] = ()
    score: int = 0


@dataclass(slots=True, frozen=True)
class PublishResult:
    status: RunStatus
    url: str | None = None
    message: str | None = None
    article_path: str | None = None
