"""SQLite Persistenz. Stdlib only, ein File, versionsierte Migrationen."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    notes        TEXT    DEFAULT '',
    project      TEXT    DEFAULT '',
    due          TEXT,
    priority     INTEGER DEFAULT 2,           -- 1 hoch, 2 normal, 3 niedrig
    status       TEXT    DEFAULT 'open',      -- open | done | dropped
    tags         TEXT    DEFAULT '',
    created_at   TEXT    NOT NULL,
    done_at      TEXT
);

CREATE TABLE IF NOT EXISTS habits (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL UNIQUE,
    cadence        TEXT    DEFAULT 'daily',   -- daily | weekly
    target_per_week INTEGER DEFAULT 7,
    active         INTEGER DEFAULT 1,
    created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS habit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id  INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    day       TEXT    NOT NULL,
    done      INTEGER DEFAULT 1,
    note      TEXT    DEFAULT '',
    UNIQUE(habit_id, day)
);

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT DEFAULT '',
    body       TEXT NOT NULL,
    tags       TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    starts_at  TEXT NOT NULL,
    ends_at    TEXT,
    location   TEXT DEFAULT '',
    notes      TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    day        TEXT NOT NULL,
    mood       INTEGER,                        -- 1..10
    energy     INTEGER,                        -- 1..10
    text       TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL UNIQUE,
    value      TEXT NOT NULL,
    category   TEXT DEFAULT 'general',
    weight     REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session    TEXT NOT NULL DEFAULT 'default',
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL UNIQUE,
    broker              TEXT DEFAULT '',
    kind                TEXT DEFAULT 'prop',    -- prop | live | demo
    currency            TEXT DEFAULT 'USD',
    start_balance       REAL NOT NULL,
    balance             REAL NOT NULL,
    max_daily_loss_pct  REAL DEFAULT 5.0,
    max_total_loss_pct  REAL DEFAULT 10.0,
    profit_target_pct   REAL DEFAULT 8.0,
    phase               TEXT DEFAULT '',
    active              INTEGER DEFAULT 1,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    symbol      TEXT NOT NULL,
    direction   TEXT NOT NULL,                 -- long | short
    opened_at   TEXT NOT NULL,
    closed_at   TEXT,
    entry       REAL,
    exit        REAL,
    stop_loss   REAL,
    take_profit REAL,
    size        REAL,
    pnl         REAL DEFAULT 0.0,
    fees        REAL DEFAULT 0.0,
    risk_amount REAL,
    r_multiple  REAL,
    setup       TEXT DEFAULT '',
    session     TEXT DEFAULT '',
    tags        TEXT DEFAULT '',
    emotion     TEXT DEFAULT '',
    rating      INTEGER,                       -- 1..5 Ausfuehrungsqualitaet
    notes       TEXT DEFAULT '',
    external_id TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE(account_id, external_id)
);

CREATE TABLE IF NOT EXISTS watchlist (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol  TEXT NOT NULL UNIQUE,
    kind    TEXT DEFAULT 'forex',
    note    TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS briefings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    day        TEXT NOT NULL UNIQUE,
    markdown   TEXT NOT NULL,
    payload    TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status  ON tasks(status, due);
CREATE INDEX IF NOT EXISTS idx_trades_opened ON trades(opened_at);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_habitlog_day  ON habit_log(day);
CREATE INDEX IF NOT EXISTS idx_messages_sess ON messages(session, id);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Duenne Schicht ueber sqlite3 - thread-safe genug fuer Scheduler + CLI."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self.migrate()

    # ------------------------------------------------------------------ core
    def migrate(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )
            self._conn.commit()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.tx() as conn:
            return conn.execute(sql, tuple(params))

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return [dict(row) for row in cur.fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def insert(self, table: str, values: dict[str, Any]) -> int:
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        cur = self.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values()))
        return int(cur.lastrowid or 0)

    def update(self, table: str, row_id: int, values: dict[str, Any]) -> None:
        if not values:
            return
        assignments = ", ".join(f"{k} = ?" for k in values)
        self.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", [*values.values(), row_id])

    def delete(self, table: str, row_id: int) -> None:
        self.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))

    # ------------------------------------------------------------------ meta
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.one("SELECT value FROM meta WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def set_json(self, key: str, value: Any) -> None:
        self.set_meta(key, json.dumps(value, ensure_ascii=False))

    def get_json(self, key: str, default: Any = None) -> Any:
        raw = self.get_meta(key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_DB: Database | None = None


def get_db(path: Path | str | None = None, *, refresh: bool = False) -> Database:
    global _DB
    if _DB is None or refresh:
        if path is None:
            from jarvis.config import get_config

            path = get_config().db_path
        _DB = Database(path)
    return _DB
