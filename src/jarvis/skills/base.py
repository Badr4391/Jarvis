"""Skill-Registry: Python-Funktionen werden zu LLM-Werkzeugen."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from jarvis.llm.base import ToolSpec

SkillFn = Callable[..., Any]


@dataclass
class Skill:
    name: str
    description: str
    properties: dict[str, dict[str, Any]]
    required: list[str]
    fn: SkillFn
    category: str = "general"
    confirm: bool = False           # aendert etwas Unwiderrufliches?

    def to_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": self.properties,
                "required": self.required,
            },
        )


REGISTRY: dict[str, Skill] = {}


def skill(
    name: str,
    description: str,
    *,
    properties: dict[str, dict[str, Any]] | None = None,
    required: list[str] | None = None,
    category: str = "general",
    confirm: bool = False,
) -> Callable[[SkillFn], SkillFn]:
    """Dekorator: registriert eine Funktion als Werkzeug fuer das Modell."""

    def decorator(fn: SkillFn) -> SkillFn:
        REGISTRY[name] = Skill(
            name=name,
            description=description.strip(),
            properties=properties or {},
            required=required or [],
            fn=fn,
            category=category,
            confirm=confirm,
        )
        return fn

    return decorator


def load_all() -> dict[str, Skill]:
    """Importiert alle Skill-Module (Seiteneffekt: Registrierung)."""
    from jarvis.skills import (  # noqa: F401
        briefing_skills,
        goal_skills,
        life_skills,
        market_skills,
        memory_skills,
        trading_skills,
    )

    return REGISTRY


def tool_specs(categories: list[str] | None = None) -> list[ToolSpec]:
    load_all()
    skills = REGISTRY.values()
    if categories:
        skills = [s for s in skills if s.category in categories]
    return [s.to_tool_spec() for s in skills]


def _coerce(value: Any, schema: dict[str, Any]) -> Any:
    """Modelle liefern Zahlen gern als String - sanft korrigieren."""
    expected = schema.get("type")
    if value is None or expected is None:
        return value
    try:
        if expected == "number" and not isinstance(value, (int, float)):
            return float(str(value).replace(",", "."))
        if expected == "integer" and not isinstance(value, int):
            return int(float(str(value)))
        if expected == "boolean" and not isinstance(value, bool):
            return str(value).strip().lower() in ("true", "ja", "yes", "1")
        if expected == "array" and isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
    except (TypeError, ValueError):
        return value
    return value


def run_skill(ctx: Any, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Skill ausfuehren; Fehler werden zu lesbaren Ergebnissen, nie zu Crashes."""
    load_all()
    target = REGISTRY.get(name)
    if target is None:
        return {"ok": False, "error": f"Unbekanntes Werkzeug: {name}"}

    args = dict(arguments or {})
    for key, schema in target.properties.items():
        if key in args:
            args[key] = _coerce(args[key], schema)

    missing = [key for key in target.required if args.get(key) in (None, "")]
    if missing:
        return {"ok": False, "error": f"Fehlende Angaben fuer {name}: {', '.join(missing)}"}

    signature = inspect.signature(target.fn)
    accepted = {k: v for k, v in args.items() if k in signature.parameters}
    try:
        result = target.fn(ctx, **accepted)
    except Exception as exc:                                   # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "result": result}


def result_to_text(payload: dict[str, Any]) -> str:
    if not payload.get("ok"):
        return f"FEHLER: {payload.get('error', 'unbekannt')}"
    result = payload.get("result")
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)[:6000]
