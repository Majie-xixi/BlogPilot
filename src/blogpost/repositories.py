from __future__ import annotations

from datetime import date, datetime, time

from blogpost.db import Database
from blogpost.domain import Run, RunStatus, Trigger


class Repository:
    def __init__(self, database: Database):
        self.database = database

    def create_run(self, trigger: Trigger) -> Run:
        run = Run.new(trigger)
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO runs(id, trigger, status, started_at) VALUES(?, ?, ?, ?)",
                (run.id, run.trigger.value, run.status.value, run.started_at.isoformat()),
            )
        return run

    def create_publish_retry(self, path: str, trigger: Trigger = Trigger.MANUAL) -> Run:
        """Create a run that republishes an already generated article."""
        run = Run.new(trigger)
        run.status = RunStatus.PUBLISHING
        with self.database.connect() as connection:
            article = connection.execute(
                "SELECT id FROM articles WHERE path = ? ORDER BY id DESC LIMIT 1", (path,)
            ).fetchone()
            connection.execute(
                "INSERT INTO runs(id, trigger, status, started_at, article_id) VALUES(?, ?, ?, ?, ?)",
                (
                    run.id,
                    run.trigger.value,
                    run.status.value,
                    run.started_at.isoformat(),
                    int(article["id"]) if article is not None else None,
                ),
            )
        return run

    def get_run(self, run_id: str) -> Run:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return Run(
            id=row["id"],
            trigger=Trigger(row["trigger"]),
            status=RunStatus(row["status"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            article_id=row["article_id"],
            error_code=row["error_code"],
            error_summary=row["error_summary"],
        )

    def update_run(
        self,
        run_id: str,
        target: RunStatus,
        *,
        article_id: int | None = None,
        error_code: str | None = None,
        error_summary: str | None = None,
    ) -> Run:
        run = self.get_run(run_id)
        run.transition(target)
        self._write_run(run, article_id, error_code, error_summary)
        return run

    def force_run_status(self, run_id: str, target: RunStatus) -> None:
        finished = datetime.now().isoformat() if target in {
            RunStatus.PUBLISHED,
            RunStatus.SKIPPED,
            RunStatus.NEEDS_REVIEW,
            RunStatus.FAILED,
            RunStatus.UNKNOWN,
        } else None
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?",
                (target.value, finished, run_id),
            )

    def _write_run(
        self,
        run: Run,
        article_id: int | None,
        error_code: str | None,
        error_summary: str | None,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """UPDATE runs SET status=?, finished_at=?, article_id=COALESCE(?, article_id),
                error_code=?, error_summary=? WHERE id=?""",
                (
                    run.status.value,
                    run.finished_at.isoformat() if run.finished_at else None,
                    article_id,
                    error_code,
                    error_summary,
                    run.id,
                ),
            )

    def has_successful_publication(self, day: date) -> bool:
        start = datetime.combine(day, time.min).isoformat()
        end = datetime.combine(day, time.max).isoformat()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM runs WHERE status=? AND finished_at BETWEEN ? AND ? LIMIT 1",
                (RunStatus.PUBLISHED.value, start, end),
            ).fetchone()
        return row is not None

    def count_successful_days(self, year: int, month: int) -> int:
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, month + 1, 1)
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(DISTINCT substr(finished_at, 1, 10)) AS total
                FROM runs WHERE status=? AND finished_at>=? AND finished_at<?""",
                (RunStatus.PUBLISHED.value, start.isoformat(), end.isoformat()),
            ).fetchone()
        return int(row["total"] or 0)

    def sync_online_publication(
        self,
        published_at: datetime,
        title: str | None,
        url: str | None,
    ) -> tuple[Run, bool]:
        """Add one idempotent history row for a publication verified online."""
        day = published_at.date()
        start = datetime.combine(day, time.min).isoformat()
        end = datetime.combine(day, time.max).isoformat()
        with self.database.connect() as connection:
            existing = connection.execute(
                """SELECT id FROM runs
                WHERE status=? AND finished_at BETWEEN ? AND ?
                ORDER BY finished_at DESC LIMIT 1""",
                (RunStatus.PUBLISHED.value, start, end),
            ).fetchone()
        if existing is not None:
            return self.get_run(str(existing["id"])), False

        label = title.strip() if title and title.strip() else "51CTO 线上文章"
        summary = f"{label} · {url}" if url else label
        run = Run.new(Trigger.SYNCED)
        run.id = f"online-sync-{day.isoformat()}"
        run.status = RunStatus.PUBLISHED
        run.started_at = published_at
        run.finished_at = published_at
        run.error_code = "online_sync"
        run.error_summary = summary
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO runs(
                id, trigger, status, started_at, finished_at, error_code, error_summary
                ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.id,
                    run.trigger.value,
                    run.status.value,
                    run.started_at.isoformat(),
                    run.finished_at.isoformat(),
                    run.error_code,
                    run.error_summary,
                ),
            )
        return self.get_run(run.id), cursor.rowcount > 0

    def add_article(
        self,
        title: str,
        path: str,
        sha256: str,
        char_count: int,
        topic: str,
        quality_json: str,
        historical: bool = False,
    ) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO articles(title,path,sha256,char_count,topic,quality_json,historical,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (title, path, sha256, char_count, topic, quality_json, int(historical), datetime.now().isoformat()),
            )
            return int(cursor.lastrowid)

    def recent_runs(self, limit: int = 20) -> list[Run]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self.get_run(row["id"]) for row in rows]

    def latest_article_path(self) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT path FROM articles ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return str(row["path"]) if row is not None else None
