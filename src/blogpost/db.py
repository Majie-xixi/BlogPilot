from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from importlib.resources import files
from pathlib import Path
import sqlite3
from collections.abc import Iterator


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        migration = (
            files("blogpost.migrations")
            .joinpath("001_initial.sql")
            .read_text(encoding="utf-8")
        )
        with self.connect() as connection:
            connection.executescript(migration)
            connection.execute(
                "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES(1, ?)",
                (datetime.now().isoformat(),),
            )
            self._migrate_multi_account(connection)

    @staticmethod
    def _has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(row["name"]) == column for row in rows)

    def _migrate_multi_account(self, connection: sqlite3.Connection) -> None:
        migration = (
            files("blogpost.migrations")
            .joinpath("002_multi_account.sql")
            .read_text(encoding="utf-8")
        )
        connection.executescript(migration)
        for table in ("runs", "topics", "articles", "publish_attempts"):
            if not self._has_column(connection, table, "account_id"):
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN account_id TEXT NOT NULL DEFAULT 'default'"
                )
        if not self._has_column(connection, "accounts", "article_type"):
            connection.execute(
                "ALTER TABLE accounts ADD COLUMN article_type TEXT NOT NULL DEFAULT '技术解析'"
            )
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_account_started
                ON runs(account_id, started_at);
            CREATE INDEX IF NOT EXISTS idx_articles_account_created
                ON articles(account_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_publish_attempts_account
                ON publish_attempts(account_id, started_at);
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES(2, ?)",
            (datetime.now().isoformat(),),
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES(3, ?)",
            (datetime.now().isoformat(),),
        )
