"""Langzeitgedaechtnis: Fakten ueber den Nutzer + Gespraechsverlauf."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from jarvis.storage.db import Database, utcnow

CATEGORIES = ("person", "ziel", "trading", "gesundheit", "arbeit", "vorliebe", "general")


@dataclass
class Memory:
    """Was Jarvis ueber dich behaelt - explizit, lesbar, loeschbar."""

    db: Database

    def remember(self, key: str, value: str, *, category: str = "general",
                 weight: float = 1.0) -> dict[str, Any]:
        key = key.strip().lower()
        now = utcnow()
        self.db.execute(
            "INSERT INTO memory(key, value, category, weight, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "category=excluded.category, weight=excluded.weight, updated_at=excluded.updated_at",
            (key, value.strip(), category, weight, now, now),
        )
        return self.db.one("SELECT * FROM memory WHERE key = ?", (key,)) or {}

    def recall(self, key: str) -> str | None:
        row = self.db.one("SELECT value FROM memory WHERE key = ?", (key.strip().lower(),))
        return row["value"] if row else None

    def forget(self, key: str) -> bool:
        cur = self.db.execute("DELETE FROM memory WHERE key = ?", (key.strip().lower(),))
        return bool(cur.rowcount)

    def search(self, needle: str, *, limit: int = 10) -> list[dict[str, Any]]:
        pattern = f"%{needle.strip().lower()}%"
        return self.db.query(
            "SELECT * FROM memory WHERE key LIKE ? OR lower(value) LIKE ? "
            "ORDER BY weight DESC, updated_at DESC LIMIT ?",
            (pattern, pattern, limit),
        )

    def all(self, *, category: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if category:
            return self.db.query(
                "SELECT * FROM memory WHERE category = ? ORDER BY weight DESC, key LIMIT ?",
                (category, limit),
            )
        return self.db.query("SELECT * FROM memory ORDER BY weight DESC, key LIMIT ?", (limit,))

    def context_block(self, *, limit: int = 25) -> str:
        """Kompakter Textblock fuers System-Prompt."""
        rows = self.all(limit=limit)
        if not rows:
            return ""
        lines = [f"- {row['key']}: {row['value']}" for row in rows]
        return "Was ich ueber dich weiss:\n" + "\n".join(lines)

    # ------------------------------------------------------------- verlauf
    def log_message(self, role: str, content: str, *, session: str = "default") -> None:
        self.db.insert(
            "messages",
            {"session": session, "role": role, "content": content, "created_at": utcnow()},
        )

    def history(self, *, session: str = "default", limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM messages WHERE session = ? ORDER BY id DESC LIMIT ?", (session, limit)
        )
        return list(reversed(rows))

    def clear_history(self, *, session: str = "default") -> None:
        self.db.execute("DELETE FROM messages WHERE session = ?", (session,))

    def prune_history(self, *, keep_days: int = 60) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
        cur = self.db.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))
        return cur.rowcount or 0
