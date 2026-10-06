"""
Download history, persisted to a small local SQLite database (stdlib only).

One HistoryService instance is created per process and shared across
requests - sqlite3 connections are cheap to open per-call, which keeps this
safe to use from multiple threads without extra locking gymnastics.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from time import time
from typing import Any, Optional

from app.config import Config
from app.utils.logger import get_logger

log = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filepath TEXT,
    url TEXT NOT NULL,
    downloaded_at REAL NOT NULL,
    resolution TEXT,
    container TEXT,
    status TEXT NOT NULL,
    error TEXT
);
"""


class HistoryService:
    def __init__(self, db_path: str | None = None, max_items: int | None = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.max_items = max_items or Config.MAX_HISTORY_ITEMS
        self._lock = threading.Lock()
        Config.ensure_dirs()
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add_entry(
        self,
        *,
        filename: str,
        url: str,
        resolution: str,
        container: str,
        status: str,
        filepath: str | None = None,
        error: str | None = None,
    ) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO history (filename, filepath, url, downloaded_at, resolution, "
                "container, status, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (filename, filepath, url, time(), resolution, container, status, error),
            )
            self._trim_locked(conn)
            return cur.lastrowid

    def _trim_locked(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "DELETE FROM history WHERE id NOT IN "
            "(SELECT id FROM history ORDER BY downloaded_at DESC LIMIT ?)",
            (self.max_items,),
        )

    def get_all(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM history ORDER BY downloaded_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get(self, entry_id: int) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM history WHERE id = ?", (entry_id,)).fetchone()
            return dict(row) if row else None

    def delete(self, entry_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM history WHERE id = ?", (entry_id,))
            return cur.rowcount > 0

    def clear(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM history")
