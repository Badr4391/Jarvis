"""Das Morgen-Briefing: alles Wichtige in einer Seite."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from jarvis.storage.db import utcnow

WEEKDAYS_DE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

GREETINGS = {
    "morning": "Guten Morgen",
    "day": "Hey",
    "evening": "Guten Abend",
}


def _part_of_day(now: datetime | None = None) -> str:
    hour = (now or datetime.now()).hour
    if hour < 11:
        return "morning"
    if hour < 18:
        return "day"
    return "evening"


@dataclass
class Briefing:
    day: str
    data: dict[str, Any] = field(default_factory=dict)
    markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"day": self.day, "data": self.data, "markdown": self.markdown}


def collect(ctx, *, day: date | None = None, include_market: bool = True) -> dict[str, Any]:
    """Sammelt alle Bausteine. Jeder Block darf einzeln leer bleiben."""
    day = day or date.today()
    cfg = ctx.config
    sections = cfg.briefing.sections
    data: dict[str, Any] = {"day": day.isoformat(), "name": cfg.user.name,
                            "part_of_day": _part_of_day()}

    if "tasks" in sections:
        data["tasks"] = ctx.life.today_tasks(today=day)
    if "agenda" in sections:
        data["agenda"] = ctx.life.agenda(day=day, days=1)
    if "habits" in sections:
        data["habits"] = ctx.life.habit_overview(today=day)
        data["mood"] = ctx.life.mood_trend()
    if "trading" in sections:
        data["trading"] = ctx.journal.daily_status(day=day.isoformat())
        data["trading"]["week"].pop("equity", None)
    if include_market and "markets" in sections:
        data["markets"] = ctx.market.snapshot()
    if include_market and "economics" in sections:
        data["economics"] = ctx.market.economic_events(days=1)
    if include_market and "news" in sections:
        data["news"] = ctx.market.news(kind="general", limit=cfg.market.news_limit)
    if "focus" in sections:
        data["focus"] = _focus(ctx, data)
    data["memory"] = ctx.memory.all(limit=8)
    return data


def _focus(ctx, data: dict[str, Any]) -> list[str]:
    """Drei konkrete Dinge fuer heute - abgeleitet, nicht geraten."""
    focus: list[str] = []
    tasks = data.get("tasks", {})
    overdue = tasks.get("overdue", []) if isinstance(tasks, dict) else []
    today = tasks.get("today", []) if isinstance(tasks, dict) else []

    if overdue:
        focus.append(f"{len(overdue)} ueberfaellige Aufgabe(n) - zuerst: {overdue[0]['title']}")
    top = [t for t in today if t.get("priority") == 1] or today
    if top:
        focus.append(f"Wichtigste Aufgabe heute: {top[0]['title']}")

    trading = data.get("trading") or {}
    guard = trading.get("guard") or {}
    if guard.get("status") == "STOP":
        focus.append("Trading: Tageslimit erreicht - heute kein Trade mehr.")
    elif guard.get("status") == "VORSICHT":
        focus.append(f"Trading: nur noch {guard.get('room', 0)} {trading.get('currency','')} Spielraum.")
    elif trading.get("realized_yesterday", 0) < 0:
        focus.append("Gestern rot - heute erst Journal lesen, dann handeln.")

    events = data.get("economics") or []
    if events:
        first = events[0]
        focus.append(f"News-Risiko: {first.get('event')} ({first.get('country')}) um {str(first.get('date',''))[11:16]}")

    habits = [h for h in data.get("habits", []) if not h.get("done_today")]
    if habits:
        focus.append(f"Offene Gewohnheit: {habits[0]['name']}")
    return focus[:4]


def render_markdown(data: dict[str, Any]) -> str:
    """Briefing als Markdown - lesbar im Terminal, im Web und als Sprachvorlage."""
    day = date.fromisoformat(data["day"])
    greeting = GREETINGS.get(data.get("part_of_day", "morning"), "Hallo")
    lines = [
        f"# {greeting}, {data.get('name', '')}",
        f"*{WEEKDAYS_DE[day.weekday()]}, {day.strftime('%d.%m.%Y')}*",
        "",
    ]

    focus = data.get("focus") or []
    if focus:
        lines += ["## Worauf es heute ankommt", *[f"{i}. {item}" for i, item in enumerate(focus, 1)], ""]

    agenda = data.get("agenda") or []
    if agenda:
        lines += ["## Termine"]
        for event in agenda:
            when = str(event.get("starts_at", ""))[11:16]
            lines.append(f"- {when + ' ' if when else ''}{event['title']}"
                         + (f" ({event['location']})" if event.get("location") else ""))
        lines.append("")

    tasks = data.get("tasks") or {}
    if any(tasks.get(k) for k in ("overdue", "today", "someday")):
        lines += ["## Aufgaben"]
        for label, key in (("Ueberfaellig", "overdue"), ("Heute", "today"), ("Ohne Datum", "someday")):
            rows = tasks.get(key) or []
            if rows:
                lines.append(f"**{label}**")
                lines += [f"- [{t['id']}] {t['title']}"
                          + (f" _(faellig {t['due']})_" if t.get("due") else "") for t in rows[:6]]
        lines.append("")

    habits = data.get("habits") or []
    if habits:
        lines += ["## Gewohnheiten"]
        for habit in habits:
            mark = "x" if habit.get("done_today") else " "
            lines.append(f"- [{mark}] {habit['name']} - Streak {habit.get('streak', 0)} Tage, "
                         f"diese Woche {habit.get('this_week', 0)}/{habit.get('target_per_week', 7)}")
        lines.append("")

    trading = data.get("trading") or {}
    if trading.get("account"):
        guard = trading.get("guard") or {}
        currency = trading.get("currency", "")
        lines += [
            "## Trading",
            f"- Konto **{trading['account']}**: {trading.get('balance')} {currency}",
            f"- Heute: {trading.get('realized_today', 0)} {currency} | "
            f"Gestern: {trading.get('realized_yesterday', 0)} {currency}",
        ]
        if guard:
            lines.append(
                f"- Wachhund: **{guard.get('status')}** - Spielraum {guard.get('room')} {currency} "
                f"(Tageslimit {guard.get('daily_loss_limit')}, bis Ziel {guard.get('target_remaining')})"
            )
        week = trading.get("week") or {}
        if week.get("trades"):
            lines.append(
                f"- 7 Tage: {week['trades']} Trades, {week['net_pnl']} {currency}, "
                f"{week['winrate']}% Treffer, PF {week['profit_factor']}"
            )
        open_trades = trading.get("open_trades") or []
        if open_trades:
            lines.append("- Offen: " + ", ".join(
                f"{t['symbol']} {t['direction']}" for t in open_trades[:5]))
        lines.append("")

    markets = data.get("markets") or []
    usable = [m for m in markets if m.get("price") is not None]
    if usable:
        lines += ["## Maerkte"]
        for row in usable:
            change = row.get("change_pct")
            arrow = "^" if (change or 0) > 0 else ("v" if (change or 0) < 0 else "-")
            change_txt = f"{change:+.2f}%" if isinstance(change, (int, float)) else "n/a"
            lines.append(f"- {arrow} **{row['symbol']}** {row['price']} ({change_txt})")
        lines.append("")

    events = data.get("economics") or []
    if events:
        lines += ["## Wirtschaftstermine heute"]
        for event in events[:8]:
            when = str(event.get("date", ""))[11:16]
            estimate = event.get("estimate")
            lines.append(
                f"- {when} {event.get('country', '')} **{event.get('event', '')}**"
                + (f" (Prognose {estimate}, zuvor {event.get('previous')})" if estimate is not None else "")
            )
        lines.append("")

    news = data.get("news") or []
    if news:
        lines += ["## Schlagzeilen"]
        lines += [f"- {n['title']}" + (f" _({n['site']})_" if n.get("site") else "") for n in news[:6]]
        lines.append("")

    if data.get("coach"):
        lines += ["## Jarvis", data["coach"], ""]

    lines.append("---")
    lines.append("_Analyse, keine Anlageberatung._")
    return "\n".join(lines)


def to_speech_text(data: dict[str, Any], *, max_items: int = 3) -> str:
    """Gekuerzte Fassung fuers Vorlesen - ohne Markdown-Zeichen."""
    greeting = GREETINGS.get(data.get("part_of_day", "morning"), "Hallo")
    parts = [f"{greeting} {data.get('name', '')}."]

    focus = (data.get("focus") or [])[:max_items]
    if focus:
        parts.append("Heute zaehlt: " + "; ".join(focus) + ".")

    trading = data.get("trading") or {}
    guard = trading.get("guard") or {}
    if guard:
        parts.append(
            f"Trading Status {guard.get('status')}. Spielraum {guard.get('room')} "
            f"{trading.get('currency', '')}."
        )

    events = data.get("economics") or []
    if events:
        names = ", ".join(e.get("event", "") for e in events[:max_items])
        parts.append(f"Achtung auf diese Termine: {names}.")

    markets = [m for m in (data.get("markets") or []) if m.get("price") is not None][:max_items]
    if markets:
        moves = ", ".join(
            f"{m['symbol']} {m.get('change_pct', 0):+.2f} Prozent"
            for m in markets if isinstance(m.get("change_pct"), (int, float))
        )
        if moves:
            parts.append(f"Maerkte: {moves}.")

    if data.get("coach"):
        parts.append(str(data["coach"]))
    return " ".join(parts)


def build(ctx, *, day: date | None = None, include_market: bool = True,
          with_llm: bool = True, save: bool = True) -> Briefing:
    """Briefing erzeugen, optional vom Modell persoenlich einleiten lassen."""
    data = collect(ctx, day=day, include_market=include_market)

    if with_llm:
        coach = _coach_line(ctx, data)
        if coach:
            data["coach"] = coach

    markdown = render_markdown(data)
    briefing = Briefing(day=data["day"], data=data, markdown=markdown)

    if save:
        ctx.db.execute(
            "INSERT INTO briefings(day, markdown, payload, created_at) VALUES(?,?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET markdown=excluded.markdown, "
            "payload=excluded.payload, created_at=excluded.created_at",
            (briefing.day, markdown, json.dumps(data, ensure_ascii=False, default=str), utcnow()),
        )
    return briefing


def _coach_line(ctx, data: dict[str, Any]) -> str:
    """Zwei bis drei persoenliche Saetze vom Modell - scheitert leise."""
    provider = ctx.llm
    if getattr(provider, "name", "") == "echo":
        return ""
    from jarvis.core.persona import build_system_prompt
    from jarvis.llm.base import Message

    payload = json.dumps(
        {k: v for k, v in data.items() if k in
         ("tasks", "habits", "trading", "economics", "focus", "mood", "memory")},
        ensure_ascii=False, default=str,
    )[:6000]

    try:
        response = provider.chat(
            [Message(role="user", content=(
                "Hier sind meine Daten fuer heute als JSON. Schreib mir zwei bis drei Saetze "
                "als Freund: was heute zaehlt, worauf ich aufpassen soll, ein ehrlicher Satz. "
                "Keine Aufzaehlung, keine Wiederholung der Zahlen, kein Motivationskitsch.\n\n"
                + payload
            ))],
            system=build_system_prompt(ctx.config, memory_block=ctx.memory.context_block()),
            max_tokens=350,
            temperature=0.7,
        )
        return response.text.strip()
    except Exception:                                          # noqa: BLE001
        return ""
