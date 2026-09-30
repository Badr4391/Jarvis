"""Benachrichtigungszentrale: speichern, verteilen, nichts doppelt senden."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from jarvis.notify.base import Notification, Notifier
from jarvis.storage.db import Database, utcnow


def build_notifiers() -> list[Notifier]:
    from jarvis.notify.ntfy import NtfyNotifier
    from jarvis.notify.telegram import TelegramNotifier

    candidates: list[Notifier] = [NtfyNotifier.from_env(), TelegramNotifier.from_env()]
    return [n for n in candidates if n.enabled()]


@dataclass
class NotificationCenter:
    """Jede Meldung landet in der Datenbank - Versand aufs Handy ist die Kuer."""

    db: Database
    notifiers: list[Notifier] = field(default_factory=build_notifiers)

    def channels(self) -> list[str]:
        return [n.name for n in self.notifiers]

    def push(self, notification: Notification, *, dedupe_hours: int = 0) -> dict[str, Any]:
        if dedupe_hours and self._recently_sent(notification, hours=dedupe_hours):
            return {"gesendet": [], "uebersprungen": "schon kuerzlich gemeldet"}

        row_id = self.db.insert(
            "notifications",
            {
                "kind": notification.kind, "title": notification.title,
                "body": notification.body, "url": notification.url,
                "priority": notification.priority, "created_at": utcnow(),
            },
        )
        delivered = [n.name for n in self.notifiers if n.send(notification)]
        if delivered:
            self.db.update("notifications", row_id, {"sent_at": utcnow()})
        return {"id": row_id, "gesendet": delivered, "kanaele": self.channels()}

    def _recently_sent(self, notification: Notification, *, hours: int) -> bool:
        cutoff = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat()
        return bool(
            self.db.one(
                "SELECT id FROM notifications WHERE kind = ? AND title = ? AND created_at >= ?",
                (notification.kind, notification.title, cutoff),
            )
        )

    # ----------------------------------------------------------------- lesen
    def inbox(self, *, limit: int = 30, unread_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM notifications"
        if unread_only:
            sql += " WHERE read_at IS NULL"
        return self.db.query(sql + " ORDER BY id DESC LIMIT ?", (limit,))

    def unread_count(self) -> int:
        row = self.db.one("SELECT COUNT(*) AS n FROM notifications WHERE read_at IS NULL")
        return int(row["n"]) if row else 0

    def mark_read(self, notification_id: int | None = None) -> int:
        if notification_id:
            self.db.update("notifications", notification_id, {"read_at": utcnow()})
            return 1
        cursor = self.db.execute(
            "UPDATE notifications SET read_at = ? WHERE read_at IS NULL", (utcnow(),)
        )
        return cursor.rowcount or 0

    def test(self) -> dict[str, Any]:
        return self.push(
            Notification(
                kind="erinnerung", title="Jarvis meldet sich",
                body="Test-Meldung. Wenn du das auf dem Handy siehst, sitzt alles.",
                tags=["wave"],
            )
        )


# --------------------------------------------------------------------- regeln


def risk_alerts(ctx) -> list[Notification]:
    """Warnen, wenn das Risikobudget knapp wird - der wichtigste Push ueberhaupt."""
    alerts: list[Notification] = []
    for account in ctx.journal.list_accounts():
        guard = ctx.journal.guard(account=account["id"])
        if not guard:
            continue
        currency = account["currency"]
        if guard.status() == "STOP":
            alerts.append(Notification(
                kind="risiko", priority=1, tags=["octagonal_sign"],
                title=f"STOP - {account['name']}",
                body=(f"Tageslimit erreicht. Heute {guard.realized_today:+.2f} {currency}. "
                      "Kein weiterer Trade."),
            ))
        elif guard.status() == "VORSICHT":
            alerts.append(Notification(
                kind="risiko", priority=1, tags=["warning"],
                title=f"Vorsicht - {account['name']}",
                body=(f"Nur noch {guard.room:.2f} {currency} Spielraum "
                      f"(heute {guard.realized_today:+.2f})."),
            ))
    return alerts


def goal_alerts(ctx) -> list[Notification]:
    """Ziele, die aus dem Tritt geraten - einmal pro Tag reicht."""
    alerts: list[Notification] = []
    overview = ctx.goals.overview()
    for goal in overview["hinter_plan"][:3]:
        unit = goal.get("unit") or ""
        alerts.append(Notification(
            kind="ziel", priority=2, tags=["dart"],
            title=f"Ziel hinter Plan: {goal['title']}",
            body=(f"{goal.get('progress_pct', 0)}% geschafft, noch {goal.get('remaining')} {unit}"
                  + (f" in {goal['days_left']} Tagen." if goal.get("days_left") is not None else ".")),
        ))
    for goal in overview["bald_faellig"][:2]:
        if goal in overview["hinter_plan"]:
            continue
        alerts.append(Notification(
            kind="ziel", priority=3, tags=["hourglass"],
            title=f"Deadline naht: {goal['title']}",
            body=f"Noch {goal['days_left']} Tage, {goal.get('progress_pct', 0)}% geschafft.",
        ))
    return alerts


def market_alerts(ctx, *, minutes_ahead: int = 45) -> list[Notification]:
    """Gleich kommen wichtige Zahlen - Zeit, Positionen zu pruefen."""
    alerts: list[Notification] = []
    now = datetime.now()
    for event in ctx.market.economic_events(days=1):
        raw = str(event.get("date") or "")
        try:
            when = datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
        minutes = (when - now).total_seconds() / 60
        if 0 <= minutes <= minutes_ahead:
            alerts.append(Notification(
                kind="markt", priority=1, tags=["chart_with_upwards_trend"],
                title=f"In {int(minutes)} Min: {event.get('event')}",
                body=(f"{event.get('country', '')} - Prognose {event.get('estimate')}, "
                      f"zuvor {event.get('previous')}. Stops pruefen."),
            ))
    return alerts


def collect_alerts(ctx) -> list[Notification]:
    alerts: list[Notification] = []
    for rule in (risk_alerts, goal_alerts, market_alerts):
        try:
            alerts.extend(rule(ctx))
        except Exception:                                          # noqa: BLE001
            continue
    return alerts
