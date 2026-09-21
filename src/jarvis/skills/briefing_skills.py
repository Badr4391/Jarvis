"""Werkzeuge fuer Briefing und Rueckblick."""

from __future__ import annotations

from datetime import date
from typing import Any

from jarvis.briefing import builder
from jarvis.skills.base import skill

STR = {"type": "string"}
BOOL = {"type": "boolean"}


@skill(
    "morning_brief",
    "Das Morgen-Briefing erzeugen: Aufgaben, Termine, Gewohnheiten, Trading-Status, "
    "Maerkte, Wirtschaftstermine, Schlagzeilen.",
    properties={"include_market": BOOL, "with_llm": BOOL},
    category="briefing",
)
def morning_brief(ctx, include_market: bool = True, with_llm: bool = False) -> dict[str, Any]:
    brief = builder.build(ctx, include_market=include_market, with_llm=with_llm)
    return {"day": brief.day, "markdown": brief.markdown}


@skill(
    "brief_read",
    "Ein frueheres Briefing nachlesen.",
    properties={"day": {**STR, "description": "ISO-Datum, leer = heute"}},
    category="briefing",
)
def brief_read(ctx, day: str = "") -> dict[str, Any]:
    row = ctx.db.one(
        "SELECT day, markdown FROM briefings WHERE day = ?", (day or date.today().isoformat(),)
    )
    return row or {"error": "Kein Briefing fuer diesen Tag"}


@skill(
    "evening_review",
    "Abend-Rueckblick: was lief heute, was ist offen, was kommt morgen.",
    category="briefing",
)
def evening_review(ctx) -> dict[str, Any]:
    today = date.today().isoformat()
    done = ctx.db.query(
        "SELECT title FROM tasks WHERE status='done' AND done_at LIKE ?", (f"{today}%",)
    )
    return {
        "erledigt": [row["title"] for row in done],
        "offen": ctx.life.today_tasks(),
        "gewohnheiten": ctx.life.habit_overview(),
        "trading": ctx.journal.daily_status(),
        "morgen": ctx.life.agenda(days=2),
        "stimmung": ctx.life.mood_trend(),
    }
