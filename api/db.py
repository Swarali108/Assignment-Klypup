"""One small storage layer for the app's own state: users, RM call notes and chat conversations.

DATABASE_URL set (Neon or any Postgres, e.g. postgresql://...?sslmode=require) -> Postgres through psycopg 3,
without prepared statements so Neon's pooled (-pooler) URL works. Tables are created on first use / API start.
Not set -> SQLite at FINSIGHT_DB_PATH (else RM_STATE_PATH, else api/state/app.sqlite).
The pipeline's outputs stay on files; only this app state lives here.

All SQL is written once with %s placeholders (and no literal percent signs). SQLite gets the same text with
%s turned into ?. Rows come back as plain dicts on both backends.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DEFAULT_PATH = Path(__file__).resolve().parent / "state" / "app.sqlite"

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
        role TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL,
        onboarded INTEGER NOT NULL DEFAULT 1)""",
    """CREATE TABLE IF NOT EXISTS rm_state (
        event_id TEXT NOT NULL, person_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'to_call',
        note TEXT NOT NULL DEFAULT '', follow_up_date TEXT, updated_at TEXT NOT NULL,
        PRIMARY KEY (event_id, person_id))""",
    """CREATE TABLE IF NOT EXISTS chat_conversations (
        id TEXT PRIMARY KEY, user_email TEXT NOT NULL, title TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
        payload TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS assignments (
        event_id TEXT NOT NULL, person_id TEXT NOT NULL, rm_email TEXT NOT NULL, assigned_by TEXT NOT NULL,
        assigned_at TEXT NOT NULL, PRIMARY KEY (event_id, person_id))""",
    """CREATE TABLE IF NOT EXISTS review_decisions (
        id TEXT PRIMARY KEY, event_id TEXT NOT NULL, kind TEXT NOT NULL, action TEXT NOT NULL, value TEXT,
        payload TEXT NOT NULL DEFAULT '{}', decided_by TEXT NOT NULL, decided_by_name TEXT NOT NULL DEFAULT '',
        decided_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS follows (
        user_email TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, label TEXT NOT NULL,
        origin_event_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, snapshot TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (user_email, kind, key))""",
    """CREATE TABLE IF NOT EXISTS alert_log (
        id TEXT NOT NULL, user_email TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL,
        link TEXT NOT NULL DEFAULT '', follow_key TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, read_at TEXT,
        PRIMARY KEY (user_email, id))""",
    "CREATE INDEX IF NOT EXISTS chat_conversations_user ON chat_conversations (user_email, updated_at)",
    "CREATE INDEX IF NOT EXISTS chat_messages_conversation ON chat_messages (conversation_id, created_at)",
)
# Columns added after a table first shipped: (table, column, definition). Added when missing.
ADDED_COLUMNS = (
    ("users", "onboarded", "INTEGER NOT NULL DEFAULT 1"),
    # Chat v2: the conversation's memory (rolling summary, focus entities, pending question), as JSON.
    ("chat_conversations", "state", "TEXT NOT NULL DEFAULT '{}'"),
    # v3: who logged the outcome, when the first call was logged, and the amount (Rs Cr) of a won deal.
    ("rm_state", "updated_by", "TEXT NOT NULL DEFAULT ''"),
    ("rm_state", "first_called_at", "TEXT"),
    ("rm_state", "won_amount_cr", "DOUBLE PRECISION"),
)

_lock = threading.Lock()
_ready: set[str] = set()


def database_url() -> str:
    """The Postgres URL, or '' when the SQLite fallback is in use. Never printed or logged."""
    return (os.environ.get("DATABASE_URL") or "").strip()


def backend() -> str:
    """'postgres' or 'sqlite'."""
    return "postgres" if database_url() else "sqlite"


def sqlite_path() -> Path:
    """Where the SQLite fallback lives (read per call so tests can point it elsewhere)."""
    return Path(os.environ.get("FINSIGHT_DB_PATH") or os.environ.get("RM_STATE_PATH") or DEFAULT_PATH)


def _key() -> str:
    """Identity of the current target, so each database is created once per process."""
    return "pg" if database_url() else f"sqlite:{sqlite_path()}"


class Conn:
    """A connection with execute/query that hides the two drivers."""

    def __init__(self, raw: Any, kind: str):
        self.raw, self.kind = raw, kind

    def _sql(self, sql: str) -> str:
        return sql if self.kind == "postgres" else sql.replace("%s", "?")

    def execute(self, sql: str, params: tuple = ()) -> None:
        """Run a statement that returns no rows."""
        self.raw.execute(self._sql(sql), params)

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Run a SELECT and return every row as a dict."""
        cursor = self.raw.execute(self._sql(sql), params)
        return [dict(row) for row in cursor.fetchall()]


@contextmanager
def connect() -> Iterator[Conn]:
    """A connection whose changes are committed when the block ends (rolled back on an error)."""
    ensure_tables()
    if database_url():
        import psycopg  # lazy: the SQLite path needs no Postgres driver
        from psycopg.rows import dict_row

        # prepare_threshold=None: no server-side prepared statements, so Neon's pooled (PgBouncer, transaction
        # mode) URL works as well as the direct one.
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=10, prepare_threshold=None) as raw:
            yield Conn(raw, "postgres")
        return
    path = sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    try:
        yield Conn(raw, "sqlite")
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def ensure_tables() -> None:
    """Create the tables once per process and target (safe to call any time, safe to repeat)."""
    key = _key()
    if key in _ready:
        return
    with _lock:
        if key in _ready:
            return
        if database_url():
            import psycopg

            with psycopg.connect(database_url(), connect_timeout=10, prepare_threshold=None) as raw:
                for statement in SCHEMA:
                    raw.execute(statement)
                for table, column, definition in ADDED_COLUMNS:
                    raw.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")
        else:
            path = sqlite_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = sqlite3.connect(path)
            try:
                for statement in SCHEMA:
                    raw.execute(statement)
                for table, column, definition in ADDED_COLUMNS:
                    have = {row[1] for row in raw.execute(f"PRAGMA table_info({table})").fetchall()}
                    if column not in have:
                        raw.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                raw.commit()
            finally:
                raw.close()
        _ready.add(key)
