from __future__ import annotations

from datetime import date, datetime, time

from blogpost.db import Database
from blogpost.domain import Account, DEFAULT_ACCOUNT_ID, Run, RunStatus, Trigger


class Repository:
    def __init__(self, database: Database):
        self.database = database

    def create_run(self, trigger: Trigger, account_id: str = DEFAULT_ACCOUNT_ID) -> Run:
        run = Run.new(trigger, account_id)
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO runs(id, trigger, status, started_at, account_id) VALUES(?, ?, ?, ?, ?)",
                (run.id, run.trigger.value, run.status.value, run.started_at.isoformat(), account_id),
            )
        return run

    def create_publish_retry(
        self,
        path: str,
        trigger: Trigger = Trigger.MANUAL,
        account_id: str = DEFAULT_ACCOUNT_ID,
    ) -> Run:
        """Create a run that republishes an already generated article."""
        run = Run.new(trigger, account_id)
        run.status = RunStatus.PUBLISHING
        with self.database.connect() as connection:
            article = connection.execute(
                "SELECT id FROM articles WHERE path = ? AND account_id = ? ORDER BY id DESC LIMIT 1",
                (path, account_id),
            ).fetchone()
            connection.execute(
                """INSERT INTO runs(id, trigger, status, started_at, article_id, account_id)
                VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    run.id,
                    run.trigger.value,
                    run.status.value,
                    run.started_at.isoformat(),
                    int(article["id"]) if article is not None else None,
                    account_id,
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
            account_id=row["account_id"],
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

    def has_successful_publication(
        self,
        day: date,
        account_id: str = DEFAULT_ACCOUNT_ID,
    ) -> bool:
        start = datetime.combine(day, time.min).isoformat()
        end = datetime.combine(day, time.max).isoformat()
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT 1 FROM runs
                WHERE account_id=? AND status=? AND finished_at BETWEEN ? AND ? LIMIT 1""",
                (account_id, RunStatus.PUBLISHED.value, start, end),
            ).fetchone()
        return row is not None

    def count_successful_days(
        self,
        year: int,
        month: int,
        account_id: str = DEFAULT_ACCOUNT_ID,
    ) -> int:
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, month + 1, 1)
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(DISTINCT substr(finished_at, 1, 10)) AS total
                FROM runs WHERE account_id=? AND status=? AND finished_at>=? AND finished_at<?""",
                (account_id, RunStatus.PUBLISHED.value, start.isoformat(), end.isoformat()),
            ).fetchone()
        return int(row["total"] or 0)

    def sync_online_publication(
        self,
        published_at: datetime,
        title: str | None,
        url: str | None,
        account_id: str = DEFAULT_ACCOUNT_ID,
    ) -> tuple[Run, bool]:
        """Add one idempotent history row for a publication verified online."""
        day = published_at.date()
        start = datetime.combine(day, time.min).isoformat()
        end = datetime.combine(day, time.max).isoformat()
        with self.database.connect() as connection:
            existing = connection.execute(
                """SELECT id FROM runs
                WHERE account_id=? AND status=? AND finished_at BETWEEN ? AND ?
                ORDER BY finished_at DESC LIMIT 1""",
                (account_id, RunStatus.PUBLISHED.value, start, end),
            ).fetchone()
        if existing is not None:
            return self.get_run(str(existing["id"])), False

        label = title.strip() if title and title.strip() else "51CTO 线上文章"
        summary = f"{label} · {url}" if url else label
        run = Run.new(Trigger.SYNCED, account_id)
        run.id = f"online-sync-{account_id}-{day.isoformat()}"
        run.status = RunStatus.PUBLISHED
        run.started_at = published_at
        run.finished_at = published_at
        run.error_code = "online_sync"
        run.error_summary = summary
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO runs(
                id, trigger, status, started_at, finished_at, error_code, error_summary, account_id
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.id,
                    run.trigger.value,
                    run.status.value,
                    run.started_at.isoformat(),
                    run.finished_at.isoformat(),
                    run.error_code,
                    run.error_summary,
                    account_id,
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
        account_id: str = DEFAULT_ACCOUNT_ID,
    ) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO articles(
                title,path,sha256,char_count,topic,quality_json,historical,created_at,account_id
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    title, path, sha256, char_count, topic, quality_json,
                    int(historical), datetime.now().isoformat(), account_id,
                ),
            )
            return int(cursor.lastrowid)

    def recent_runs(
        self,
        limit: int = 20,
        account_id: str | None = None,
    ) -> list[Run]:
        with self.database.connect() as connection:
            if account_id is None:
                rows = connection.execute(
                    "SELECT id FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT id FROM runs WHERE account_id=?
                    ORDER BY started_at DESC LIMIT ?""",
                    (account_id, limit),
                ).fetchall()
        return [self.get_run(row["id"]) for row in rows]

    def latest_article_path(self, account_id: str | None = None) -> str | None:
        with self.database.connect() as connection:
            if account_id is None:
                row = connection.execute(
                    "SELECT path FROM articles ORDER BY created_at DESC, id DESC LIMIT 1"
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT path FROM articles WHERE account_id=?
                    ORDER BY created_at DESC, id DESC LIMIT 1""",
                    (account_id,),
                ).fetchone()
        return str(row["path"]) if row is not None else None

    def list_accounts(self, *, enabled_only: bool = False) -> list[Account]:
        query = "SELECT * FROM accounts"
        params: tuple[object, ...] = ()
        if enabled_only:
            query += " WHERE enabled=1"
        query += " ORDER BY sort_order, created_at, id"
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._account_from_row(row) for row in rows]

    def get_account(self, account_id: str = DEFAULT_ACCOUNT_ID) -> Account:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM accounts WHERE id=?", (account_id,)
            ).fetchone()
        if row is None:
            raise KeyError(account_id)
        return self._account_from_row(row)

    def save_account(self, account: Account) -> Account:
        account.validate()
        now = datetime.now().isoformat()
        with self.database.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM accounts WHERE id=?", (account.id,)
            ).fetchone()
            if exists is None:
                total = int(connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0])
                if total >= 5:
                    raise ValueError("最多只能配置 5 个账号")
            connection.execute(
                """INSERT INTO accounts(
                id,display_name,profile_url,enabled,sort_order,schedule_time,monthly_target,
                category,secondary_category,personal_category,content_directions,keywords,
                article_subdir,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                display_name=excluded.display_name,profile_url=excluded.profile_url,
                enabled=excluded.enabled,sort_order=excluded.sort_order,
                schedule_time=excluded.schedule_time,monthly_target=excluded.monthly_target,
                category=excluded.category,secondary_category=excluded.secondary_category,
                personal_category=excluded.personal_category,
                content_directions=excluded.content_directions,keywords=excluded.keywords,
                article_subdir=excluded.article_subdir,updated_at=excluded.updated_at""",
                (
                    account.id, account.display_name, account.profile_url, int(account.enabled),
                    account.sort_order, account.schedule_time.strftime("%H:%M"),
                    account.monthly_target, account.category, account.secondary_category,
                    account.personal_category, account.content_directions, account.keywords,
                    account.article_subdir, now, now,
                ),
            )
        return self.get_account(account.id)

    def update_default_account_from_legacy(
        self,
        *,
        profile_url: str,
        category: str,
        schedule_time: time,
    ) -> Account:
        current = self.get_account(DEFAULT_ACCOUNT_ID)
        account = Account(
            id=current.id,
            display_name=current.display_name,
            profile_url=current.profile_url or profile_url,
            enabled=current.enabled,
            sort_order=current.sort_order,
            schedule_time=(
                schedule_time
                if current.schedule_time == time(10, 0)
                else current.schedule_time
            ),
            monthly_target=current.monthly_target,
            category=category if current.category == "AI 智能体" else current.category,
            secondary_category=current.secondary_category,
            personal_category=current.personal_category,
            content_directions=current.content_directions,
            keywords=current.keywords,
            article_subdir=current.article_subdir,
        )
        return self.save_account(account)

    @staticmethod
    def _account_from_row(row) -> Account:
        hour, minute = str(row["schedule_time"]).split(":", 1)
        return Account(
            id=str(row["id"]),
            display_name=str(row["display_name"]),
            profile_url=str(row["profile_url"]),
            enabled=bool(row["enabled"]),
            sort_order=int(row["sort_order"]),
            schedule_time=time(int(hour), int(minute)),
            monthly_target=int(row["monthly_target"]),
            category=str(row["category"]),
            secondary_category=str(row["secondary_category"]),
            personal_category=str(row["personal_category"]),
            content_directions=str(row["content_directions"]),
            keywords=str(row["keywords"]),
            article_subdir=str(row["article_subdir"]),
        )
