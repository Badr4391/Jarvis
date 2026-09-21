"""Werkzeuge fuers Gedaechtnis - damit Jarvis dich wirklich kennt."""

from __future__ import annotations

from typing import Any

from jarvis.skills.base import skill

STR = {"type": "string"}


@skill(
    "memory_remember",
    "Dauerhaft merken: Ziele, Regeln, Vorlieben, wichtige Menschen. "
    "Schluessel kurz und sprechend waehlen (z.B. 'ziel_2026', 'risiko_regel').",
    properties={
        "key": STR,
        "value": STR,
        "category": {**STR, "description": "person | ziel | trading | gesundheit | arbeit | vorliebe | general"},
    },
    required=["key", "value"],
    category="memory",
)
def memory_remember(ctx, key: str, value: str, category: str = "general") -> dict[str, Any]:
    return ctx.memory.remember(key, value, category=category)


@skill(
    "memory_recall",
    "Gespeichertes Wissen suchen.",
    properties={"query": STR},
    required=["query"],
    category="memory",
)
def memory_recall(ctx, query: str) -> list[dict[str, Any]]:
    return ctx.memory.search(query)


@skill("memory_list", "Alles auflisten, was Jarvis ueber dich gespeichert hat.", category="memory")
def memory_list(ctx) -> list[dict[str, Any]]:
    return ctx.memory.all()


@skill(
    "memory_forget",
    "Einen gespeicherten Eintrag loeschen.",
    properties={"key": STR},
    required=["key"],
    category="memory",
    confirm=True,
)
def memory_forget(ctx, key: str) -> dict[str, Any]:
    return {"key": key, "geloescht": ctx.memory.forget(key)}
