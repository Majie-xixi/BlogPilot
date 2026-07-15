from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import uuid


class Trigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


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

    @classmethod
    def new(cls, trigger: Trigger) -> "Run":
        return cls(id=str(uuid.uuid4()), trigger=trigger)

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
