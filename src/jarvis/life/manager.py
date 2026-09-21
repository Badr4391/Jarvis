"""Leben ordnen: Aufgaben, Gewohnheiten, Notizen, Termine, Tagebuch."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from jarvis.storage.db import Database, utcnow

PRIORITY_WORDS = {
    "hoch": 1, "high": 1, "wichtig": 1, "dringend": 1, "!": 1,
    "normal": 2, "mittel": 2,
    "niedrig": 3, "low": 3, "irgendwann": 3,
}

_RELATIVE = {
    "heute": 0, "today": 0,
    "morgen": 1, "tomorrow": 1,
    "uebermorgen": 2, "übermorgen": 2,
}

_WEEKDAYS = {
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonntag": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def parse_when(text: str | None, *, today: date | None = None) -> str | None:
    """Erkennt 'heute', 'morgen', 'freitag', '2026-09-24', '24.09.' oder '24.09.2026'."""
    if not text:
        return None
    raw = text.strip().lower()
    today = today or date.today()

    if raw in _RELATIVE:
        return (today + timedelta(days=_RELATIVE[raw])).isoformat()

    if raw.startswith("in ") and "tag" in raw:
        digits = re.findall(r"\d+", raw)
        if digits:
            return (today + timedelta(days=int(digits[0]))).isoformat()

    if raw in _WEEKDAYS:
        delta = (_WEEKDAYS[raw] - today.weekday()) % 7 or 7
        return (today + timedelta(days=delta)).isoformat()

    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if iso:
        return raw

    german = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.?(\d{4})?", raw)
    if german:
        day, month, year = german.groups()
        year_int = int(year) if year else today.year
        try:
            parsed = date(year_int, int(month), int(day))
        except ValueError:
            return None
        if not year and parsed < today:
            parsed = parsed.replace(year=year_int + 1)
        return parsed.isoformat()

    return None


@dataclass
class LifeManager:
    """Alle Lebens-Domaenen in einem schmalen, testbaren Objekt."""

    db: Database

    # ----------------------------------------------------------------- tasks
    def add_task(
        self,
        title: str,
        *,
        due: str | None = None,
        priority: int | str = 2,
        project: str = "",
        notes: str = "",
        tags: str = "",
    ) -> dict[str, Any]:
        if isinstance(priority, str):
            priority = PRIORITY_WORDS.get(priority.strip().lower(), 2)
        priority = min(3, max(1, int(priority)))
        task_id = self.db.insert(
            "tasks",
            {
                "title": title.strip(),
                "notes": notes,
                "project": project,
                "due": parse_when(due) or (due if due else None),
                "priority": priority,
                "status": "open",
                "tags": tags,
                "created_at": utcnow(),
            },
        )
        return self.get_task(task_id) or {}

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM tasks WHERE id = ?", (task_id,))

    def list_tasks(
        self,
        *,
        status: str = "open",
        due_before: str | None = None,
        project: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM tasks WHERE 1=1"
        params: list[Any] = []
        if status and status != "all":
            sql += " AND status = ?"
            params.append(status)
        if due_before:
            sql += " AND due IS NOT NULL AND due <= ?"
            params.append(due_before)
        if project:
            sql += " AND project = ?"
            params.append(project)
        sql += " ORDER BY (due IS NULL), due ASC, priority ASC, id ASC LIMIT ?"
        params.append(limit)
        return self.db.query(sql, params)

    def today_tasks(self, *, today: date | None = None) -> dict[str, list[dict[str, Any]]]:
        today = today or date.today()
        iso = today.isoformat()
        overdue = self.db.query(
            "SELECT * FROM tasks WHERE status='open' AND due IS NOT NULL AND due < ? "
            "ORDER BY due ASC, priority ASC",
            (iso,),
        )
        due_today = self.db.query(
            "SELECT * FROM tasks WHERE status='open' AND due = ? ORDER BY priority ASC", (iso,)
        )
        no_date = self.db.query(
            "SELECT * FROM tasks WHERE status='open' AND due IS NULL "
            "ORDER BY priority ASC, id ASC LIMIT 5"
        )
        return {"overdue": overdue, "today": due_today, "someday": no_date}

    def complete_task(self, task_id: int) -> dict[str, Any] | None:
        self.db.update("tasks", task_id, {"status": "done", "done_at": utcnow()})
        return self.get_task(task_id)

    def drop_task(self, task_id: int) -> None:
        self.db.update("tasks", task_id, {"status": "dropped", "done_at": utcnow()})

    def find_task(self, needle: str) -> dict[str, Any] | None:
        return self.db.one(
            "SELECT * FROM tasks WHERE status='open' AND lower(title) LIKE ? ORDER BY id LIMIT 1",
            (f"%{needle.strip().lower()}%",),
        )

    # ---------------------------------------------------------------- habits
    def add_habit(self, name: str, *, cadence: str = "daily", target_per_week: int = 7) -> dict[str, Any]:
        self.db.execute(
            "INSERT INTO habits(name, cadence, target_per_week, active, created_at) "
            "VALUES(?,?,?,1,?) ON CONFLICT(name) DO UPDATE SET active=1, "
            "cadence=excluded.cadence, target_per_week=excluded.target_per_week",
            (name.strip(), cadence, target_per_week, utcnow()),
        )
        return self.db.one("SELECT * FROM habits WHERE name = ?", (name.strip(),)) or {}

    def log_habit(self, name: str, *, day: str | None = None, done: bool = True, note: str = "") -> bool:
        habit = self.db.one("SELECT * FROM habits WHERE lower(name) = ?", (name.strip().lower(),))
        if not habit:
            habit = self.add_habit(name)
        day = day or date.today().isoformat()
        self.db.execute(
            "INSERT INTO habit_log(habit_id, day, done, note) VALUES(?,?,?,?) "
            "ON CONFLICT(habit_id, day) DO UPDATE SET done=excluded.done, note=excluded.note",
            (habit["id"], day, 1 if done else 0, note),
        )
        return True

    def habit_streak(self, habit_id: int, *, today: date | None = None) -> int:
        today = today or date.today()
        days = {
            row["day"]
            for row in self.db.query(
                "SELECT day FROM habit_log WHERE habit_id = ? AND done = 1", (habit_id,)
            )
        }
        streak, cursor = 0, today
        if cursor.isoformat() not in days:          # heute noch offen -> ab gestern zaehlen
            cursor -= timedelta(days=1)
        while cursor.isoformat() in days:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    def habit_overview(self, *, today: date | None = None) -> list[dict[str, Any]]:
        today = today or date.today()
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        out = []
        for habit in self.db.query("SELECT * FROM habits WHERE active = 1 ORDER BY name"):
            done_today = self.db.one(
                "SELECT 1 AS hit FROM habit_log WHERE habit_id=? AND day=? AND done=1",
                (habit["id"], today.isoformat()),
            )
            week = self.db.one(
                "SELECT COUNT(*) AS n FROM habit_log WHERE habit_id=? AND day>=? AND done=1",
                (habit["id"], week_start),
            )
            out.append(
                {
                    **habit,
                    "done_today": bool(done_today),
                    "this_week": int(week["n"]) if week else 0,
                    "streak": self.habit_streak(habit["id"], today=today),
                }
            )
        return out

    # ----------------------------------------------------------------- notes
    def add_note(self, body: str, *, title: str = "", tags: str = "") -> dict[str, Any]:
        note_id = self.db.insert(
            "notes", {"title": title, "body": body, "tags": tags, "created_at": utcnow()}
        )
        return self.db.one("SELECT * FROM notes WHERE id = ?", (note_id,)) or {}

    def search_notes(self, needle: str, *, limit: int = 20) -> list[dict[str, Any]]:
        pattern = f"%{needle.strip().lower()}%"
        return self.db.query(
            "SELECT * FROM notes WHERE lower(body) LIKE ? OR lower(title) LIKE ? OR lower(tags) LIKE ? "
            "ORDER BY id DESC LIMIT ?",
            (pattern, pattern, pattern, limit),
        )

    # ---------------------------------------------------------------- events
    def add_event(
        self, title: str, starts_at: str, *, ends_at: str | None = None,
        location: str = "", notes: str = ""
    ) -> dict[str, Any]:
        normalized = parse_when(starts_at) or starts_at
        event_id = self.db.insert(
            "events",
            {
                "title": title,
                "starts_at": normalized,
                "ends_at": ends_at,
                "location": location,
                "notes": notes,
                "created_at": utcnow(),
            },
        )
        return self.db.one("SELECT * FROM events WHERE id = ?", (event_id,)) or {}

    def agenda(self, *, day: date | None = None, days: int = 1) -> list[dict[str, Any]]:
        start = (day or date.today()).isoformat()
        end = ((day or date.today()) + timedelta(days=days)).isoformat()
        return self.db.query(
            "SELECT * FROM events WHERE starts_at >= ? AND starts_at < ? ORDER BY starts_at",
            (start, end + "T23:59:59"),
        )

    # --------------------------------------------------------------- journal
    def add_journal(
        self, text: str, *, mood: int | None = None, energy: int | None = None,
        day: str | None = None
    ) -> dict[str, Any]:
        entry_id = self.db.insert(
            "journal",
            {
                "day": day or date.today().isoformat(),
                "mood": mood,
                "energy": energy,
                "text": text,
                "created_at": utcnow(),
            },
        )
        return self.db.one("SELECT * FROM journal WHERE id = ?", (entry_id,)) or {}

    def recent_journal(self, *, limit: int = 7) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM journal ORDER BY id DESC LIMIT ?", (limit,))

    def mood_trend(self, *, days: int = 14) -> dict[str, Any]:
        since = (date.today() - timedelta(days=days)).isoformat()
        rows = self.db.query(
            "SELECT mood, energy FROM journal WHERE day >= ? AND mood IS NOT NULL", (since,)
        )
        if not rows:
            return {"days": days, "entries": 0, "avg_mood": None, "avg_energy": None}
        moods = [r["mood"] for r in rows if r["mood"] is not None]
        energies = [r["energy"] for r in rows if r["energy"] is not None]
        return {
            "days": days,
            "entries": len(rows),
            "avg_mood": round(sum(moods) / len(moods), 1) if moods else None,
            "avg_energy": round(sum(energies) / len(energies), 1) if energies else None,
        }
