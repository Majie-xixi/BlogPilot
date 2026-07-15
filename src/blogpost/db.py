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
