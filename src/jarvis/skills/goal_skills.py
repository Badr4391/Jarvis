"""Werkzeuge fuer Ziele und Kontostaende."""

from __future__ import annotations

from typing import Any

from jarvis.skills.base import skill

STR = {"type": "string"}
NUM = {"type": "number"}
INT = {"type": "integer"}


@skill(
    "goal_add",
    "Neues Ziel anlegen. Messbar mit Zielwert und Deadline, damit Jarvis das Tempo "
    "ausrechnen kann. Mit metric='balance' und einem Konto aktualisiert es sich selbst.",
    properties={
        "title": STR,
        "target_value": {**NUM, "description": "Zielzahl, z.B. 108000"},
        "start_value": {**NUM, "description": "Ausgangswert, z.B. 100000"},
        "current_value": NUM,
        "unit": {**STR, "description": "USD, EUR, kg, Trades ..."},
        "deadline": {**STR, "description": "'freitag', '2026-12-31' oder leer"},
        "category": {**STR, "description": "trading | geld | gesundheit | arbeit | privat"},
        "why": {**STR, "description": "Warum ist dir das wichtig?"},
        "account": {**STR, "description": "Konto fuer automatische Fortschritte"},
        "metric": {**STR, "description": "balance | profit | winrate | trades"},
    },
    required=["title"],
    category="goals",
)
def goal_add(ctx, title: str, **kwargs) -> dict[str, Any]:
    clean = {k: v for k, v in kwargs.items() if v not in (None, "")}
    return ctx.goals.add(title, **clean)


@skill(
    "goal_list",
    "Alle Ziele mit Fortschritt, Tempo und Restweg.",
    properties={"status": {**STR, "description": "active | done | all"}, "category": STR},
    category="goals",
)
def goal_list(ctx, status: str = "active", category: str = "") -> dict[str, Any]:
    ctx.goals.sync_auto_goals(ctx.journal)
    return {"ziele": ctx.goals.list(status=status, category=category or None),
            "uebersicht": {k: v for k, v in ctx.goals.overview().items() if k != "ziele"}}


@skill(
    "goal_progress",
    "Fortschritt auf einem Ziel eintragen. Ziel per id oder Stichwort.",
    properties={"id": INT, "title": {**STR, "description": "Stichwort aus dem Zieltitel"},
                "value": {**NUM, "description": "neuer Stand"}, "note": STR},
    required=["value"],
    category="goals",
)
def goal_progress(ctx, value: float, id: int | None = None, title: str = "",
                  note: str = "") -> dict[str, Any]:
    goal = ctx.goals.get(id) if id else ctx.goals.find(title)
    if not goal:
        return {"error": "Ziel nicht gefunden"}
    return ctx.goals.log_progress(goal["id"], value, note=note) or {}


@skill(
    "goal_done",
    "Ziel als erreicht markieren.",
    properties={"id": INT, "title": STR},
    category="goals",
)
def goal_done(ctx, id: int | None = None, title: str = "") -> dict[str, Any]:
    goal = ctx.goals.get(id) if id else ctx.goals.find(title)
    if not goal:
        return {"error": "Ziel nicht gefunden"}
    return ctx.goals.complete(goal["id"]) or {}


@skill(
    "accounts_sync",
    "Kontostaende beim Anbieter abfragen (FundedNext) und aktualisieren.",
    category="accounts",
)
def accounts_sync(ctx) -> dict[str, Any]:
    result = ctx.sync.run()
    result["ziele_aktualisiert"] = [g["title"] for g in ctx.goals.sync_auto_goals(ctx.journal)]
    return result


@skill(
    "portfolio",
    "Alle Konten auf einen Blick: Stand, Gewinn, Risikopuffer, Verlauf.",
    category="accounts",
)
def portfolio(ctx) -> dict[str, Any]:
    return ctx.sync.portfolio()


@skill(
    "account_balance_set",
    "Kontostand von Hand setzen (wenn keine Anbindung eingerichtet ist).",
    properties={"account": STR, "balance": NUM},
    required=["account", "balance"],
    category="accounts",
)
def account_balance_set(ctx, account: str, balance: float) -> dict[str, Any]:
    updated = ctx.journal.set_balance(account, balance)
    if not updated:
        return {"error": f"Konto {account} nicht gefunden"}
    ctx.sync.record_balance(updated["id"], balance, source="manual")
    ctx.goals.sync_auto_goals(ctx.journal)
    return updated


@skill(
    "notify_send",
    "Eine Meldung aufs Handy schicken (ntfy oder Telegram).",
    properties={
        "title": STR, "body": STR,
        "kind": {**STR, "description": "brief | risiko | ziel | erinnerung | markt"},
        "priority": {**INT, "description": "1 hoch, 2 normal, 3 leise"},
    },
    required=["title"],
    category="notify",
)
def notify_send(ctx, title: str, body: str = "", kind: str = "erinnerung",
                priority: int = 2) -> dict[str, Any]:
    from jarvis.notify.base import Notification

    return ctx.notify.push(Notification(kind=kind, title=title, body=body, priority=priority))


@skill(
    "alerts_check",
    "Pruefen, ob gerade etwas dringend ist: Risikolimits, Ziele hinter Plan, "
    "wichtige Wirtschaftstermine in Kuerze.",
    properties={"send": {"type": "boolean", "description": "auch aufs Handy schicken"}},
    category="notify",
)
def alerts_check(ctx, send: bool = False) -> dict[str, Any]:
    from jarvis.notify.center import collect_alerts

    alerts = collect_alerts(ctx)
    if send:
        for alert in alerts:
            ctx.notify.push(alert, dedupe_hours=4)
    return {"anzahl": len(alerts), "meldungen": [a.to_dict() for a in alerts],
            "gesendet": send, "kanaele": ctx.notify.channels()}
