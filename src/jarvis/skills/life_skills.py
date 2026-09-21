"""Werkzeuge fuers Leben: Aufgaben, Gewohnheiten, Notizen, Termine, Tagebuch."""

from __future__ import annotations

from datetime import date
from typing import Any

from jarvis.skills.base import skill

STR = {"type": "string"}
NUM = {"type": "number"}
INT = {"type": "integer"}


@skill(
    "task_add",
    "Neue Aufgabe anlegen. Faelligkeit versteht 'heute', 'morgen', 'freitag', '24.09.' oder ISO-Datum.",
    properties={
        "title": {**STR, "description": "Worum geht es?"},
        "due": {**STR, "description": "Faellig wann, z.B. 'morgen' oder '2026-09-30'"},
        "priority": {**STR, "description": "hoch | normal | niedrig"},
        "project": {**STR, "description": "Projekt oder Lebensbereich"},
        "notes": STR,
    },
    required=["title"],
    category="life",
)
def task_add(ctx, title: str, due: str = "", priority: str = "normal",
             project: str = "", notes: str = "") -> dict[str, Any]:
    return ctx.life.add_task(title, due=due or None, priority=priority, project=project, notes=notes)


@skill(
    "task_list",
    "Offene Aufgaben auflisten - standardmaessig alles was heute ansteht plus Ueberfaelliges.",
    properties={
        "status": {**STR, "description": "open | done | all"},
        "project": STR,
        "limit": INT,
    },
    category="life",
)
def task_list(ctx, status: str = "open", project: str = "", limit: int = 25) -> dict[str, Any]:
    return {
        "heute": ctx.life.today_tasks(),
        "liste": ctx.life.list_tasks(status=status, project=project or None, limit=limit),
    }


@skill(
    "task_done",
    "Aufgabe als erledigt markieren. Entweder per id oder per Stichwort aus dem Titel.",
    properties={"id": INT, "title": {**STR, "description": "Stichwort aus dem Aufgabentitel"}},
    category="life",
)
def task_done(ctx, id: int | None = None, title: str = "") -> dict[str, Any]:
    task = ctx.life.get_task(id) if id else ctx.life.find_task(title)
    if not task:
        return {"error": "Keine passende Aufgabe gefunden"}
    return ctx.life.complete_task(task["id"]) or {}


@skill(
    "habit_log",
    "Gewohnheit fuer heute abhaken (legt sie bei Bedarf an).",
    properties={"name": STR, "done": {"type": "boolean"}, "note": STR},
    required=["name"],
    category="life",
)
def habit_log(ctx, name: str, done: bool = True, note: str = "") -> dict[str, Any]:
    ctx.life.log_habit(name, done=done, note=note)
    return {"habit": name, "done": done, "uebersicht": ctx.life.habit_overview()}


@skill(
    "habit_overview",
    "Alle Gewohnheiten mit Streak und Wochenfortschritt.",
    category="life",
)
def habit_overview(ctx) -> list[dict[str, Any]]:
    return ctx.life.habit_overview()


@skill(
    "note_add",
    "Gedanken, Idee oder Info festhalten.",
    properties={"body": STR, "title": STR, "tags": {**STR, "description": "kommagetrennt"}},
    required=["body"],
    category="life",
)
def note_add(ctx, body: str, title: str = "", tags: str = "") -> dict[str, Any]:
    return ctx.life.add_note(body, title=title, tags=tags)


@skill(
    "note_search",
    "Notizen durchsuchen.",
    properties={"query": STR},
    required=["query"],
    category="life",
)
def note_search(ctx, query: str) -> list[dict[str, Any]]:
    return ctx.life.search_notes(query)


@skill(
    "event_add",
    "Termin eintragen.",
    properties={
        "title": STR,
        "starts_at": {**STR, "description": "'morgen', '2026-09-30' oder '2026-09-30T14:00'"},
        "location": STR,
        "notes": STR,
    },
    required=["title", "starts_at"],
    category="life",
)
def event_add(ctx, title: str, starts_at: str, location: str = "", notes: str = "") -> dict[str, Any]:
    return ctx.life.add_event(title, starts_at, location=location, notes=notes)


@skill(
    "agenda",
    "Termine der naechsten Tage.",
    properties={"days": INT},
    category="life",
)
def agenda(ctx, days: int = 3) -> list[dict[str, Any]]:
    return ctx.life.agenda(days=days)


@skill(
    "journal_add",
    "Tagebucheintrag mit Stimmung (1-10) und Energie (1-10).",
    properties={"text": STR, "mood": INT, "energy": INT},
    required=["text"],
    category="life",
)
def journal_add(ctx, text: str, mood: int | None = None, energy: int | None = None) -> dict[str, Any]:
    entry = ctx.life.add_journal(text, mood=mood, energy=energy)
    return {"eintrag": entry, "trend": ctx.life.mood_trend()}


@skill(
    "day_overview",
    "Kompletter Tagesueberblick: Aufgaben, Termine, Gewohnheiten, Stimmungstrend.",
    category="life",
)
def day_overview(ctx) -> dict[str, Any]:
    return {
        "datum": date.today().isoformat(),
        "aufgaben": ctx.life.today_tasks(),
        "termine": ctx.life.agenda(days=1),
        "gewohnheiten": ctx.life.habit_overview(),
        "stimmung": ctx.life.mood_trend(),
    }
