"""Tiny synchronous database facade.

* SQL is written once with ``?`` placeholders and portable column types (TEXT / BIGINT).
* ``SqliteDatabase``   local development and tests (file or ``:memory:``).
* ``PostgresDatabase`` production (Neon / Supabase). Imports ``psycopg`` lazily so the rest of
  the app runs without it. NOTE: written to the psycopg 3 API but NOT exercised in the sandbox
  that produced it (no network, driver not installable) -- run the auth tests against a real
  Postgres before relying on it (docs/KNOWN_ISSUES.md).
Always pass user input as parameters; never format it into the SQL string.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Sequence

log = logging.getLogger("kpt.db")
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Database:
    """Interface: ``execute`` -> rowcount, ``one`` -> dict | None, ``all`` -> list[dict]."""

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:  # pragma: no cover - interface
        raise NotImplementedError

    def one(self, sql: str, params: Sequence[Any] = ()) -> dict | None:  # pragma: no cover
        raise NotImplementedError

    def all(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:  # pragma: no cover
        raise NotImplementedError

    def migrate(self) -> list[str]:
        """Apply unapplied ``migrations/NNNN_*.sql`` files in order; returns the versions applied."""
        self.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at BIGINT NOT NULL)")
        done = {r["version"] for r in self.all("SELECT version FROM schema_migrations")}
        applied: list[str] = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.stem in done:
                continue
            for statement in (s.strip() for s in path.read_text(encoding="utf-8").split(";")):
                if statement:
                    self.execute(statement)
            self.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (path.stem, _now()))
            applied.append(path.stem)
        return applied


def _now() -> int:
    import time
    return int(time.time())


class SqliteDatabase(Database):
    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()

    def execute(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, tuple(params)).rowcount

    def one(self, sql, params=()):
        with self._lock:
            row = self._conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None

    def all(self, sql, params=()):
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, tuple(params)).fetchall()]


class PostgresDatabase(Database):
    def __init__(self, url: str) -> None:
        self._url, self._conn, self._lock = url, None, threading.RLock()

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self._url, autocommit=True, row_factory=dict_row, connect_timeout=5)

    def _run(self, sql: str, params, fetch: str):
        sql = sql.replace("?", "%s")
        with self._lock:
            for attempt in (1, 2):  # one transparent reconnect: serverless connections go stale
                try:
                    if self._conn is None or self._conn.closed:
                        self._conn = self._connect()
                    cur = self._conn.execute(sql, tuple(params))
                    if fetch == "one":
                        return cur.fetchone()
                    if fetch == "all":
                        return cur.fetchall()
                    return cur.rowcount
                except Exception as exc:  # noqa: BLE001
                    if attempt == 1 and type(exc).__name__ in {"OperationalError", "InterfaceError"}:
                        self._conn = None
                        continue
                    raise

    def execute(self, sql, params=()):
        return self._run(sql, params, "none")

    def one(self, sql, params=()):
        return self._run(sql, params, "one")

    def all(self, sql, params=()):
        return self._run(sql, params, "all")


def open_database(database_url: str | None, *, local_path: str = ":memory:") -> Database:
    """Postgres when ``DATABASE_URL`` is set, otherwise SQLite at ``local_path``."""
    db: Database = PostgresDatabase(database_url) if database_url else SqliteDatabase(local_path)
    applied = db.migrate()
    if applied:
        log.info("applied migrations: %s", ", ".join(applied))
    return db
