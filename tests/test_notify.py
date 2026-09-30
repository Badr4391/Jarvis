"""Benachrichtigungen: speichern, verteilen, Warnregeln."""

from datetime import date, timedelta

import pytest

from jarvis.notify.base import Notification
from jarvis.notify.center import (
    NotificationCenter,
    collect_alerts,
    goal_alerts,
    risk_alerts,
)


class FakeNotifier:
    """Merkt sich, was verschickt worden waere."""

    def __init__(self, name="fake", works=True):
        self.name = name
        self.works = works
        self.sent: list[Notification] = []

    def enabled(self) -> bool:
        return True

    def send(self, notification: Notification) -> bool:
        self.sent.append(notification)
        return self.works


@pytest.fixture()
def center(db):
    return NotificationCenter(db=db, notifiers=[])


def test_message_is_stored_even_without_channel(center):
    center.push(Notification(kind="risiko", title="STOP"))
    assert [n["title"] for n in center.inbox()] == ["STOP"]
    assert center.unread_count() == 1


def test_delivery_over_channels(db):
    good, bad = FakeNotifier("gut"), FakeNotifier("kaputt", works=False)
    center = NotificationCenter(db=db, notifiers=[good, bad])
    result = center.push(Notification(kind="brief", title="Guten Morgen"))
    assert result["gesendet"] == ["gut"]
    assert len(good.sent) == 1 and len(bad.sent) == 1     # versucht wurde beides


def test_dedupe_suppresses_repeats(center):
    center.push(Notification(kind="risiko", title="STOP - FN"), dedupe_hours=6)
    second = center.push(Notification(kind="risiko", title="STOP - FN"), dedupe_hours=6)
    assert "uebersprungen" in second
    assert len(center.inbox()) == 1


def test_dedupe_only_matches_same_title(center):
    center.push(Notification(kind="risiko", title="STOP - A"), dedupe_hours=6)
    center.push(Notification(kind="risiko", title="STOP - B"), dedupe_hours=6)
    assert len(center.inbox()) == 2


def test_mark_read(center):
    center.push(Notification(kind="ziel", title="eins"))
    center.push(Notification(kind="ziel", title="zwei"))
    assert center.mark_read() == 2
    assert center.unread_count() == 0


def test_unread_only_filter(center):
    first = center.push(Notification(kind="ziel", title="eins"))
    center.push(Notification(kind="ziel", title="zwei"))
    center.mark_read(first["id"])
    assert [n["title"] for n in center.inbox(unread_only=True)] == ["zwei"]


# ------------------------------------------------------------------ regeln


def test_risk_alert_on_stop(ctx):
    ctx.journal.add_account("FN", start_balance=100_000)
    ctx.journal.log_trade(symbol="X", direction="long", pnl=-5_000,
                          closed_at=f"{date.today().isoformat()}T10:00:00")
    alerts = risk_alerts(ctx)
    assert alerts and alerts[0].title.startswith("STOP")
    assert alerts[0].priority == 1


def test_risk_alert_warns_before_the_limit(ctx):
    ctx.journal.add_account("FN", start_balance=100_000)
    ctx.journal.log_trade(symbol="X", direction="long", pnl=-4_900,
                          closed_at=f"{date.today().isoformat()}T10:00:00")
    assert risk_alerts(ctx)[0].title.startswith("Vorsicht")


def test_no_risk_alert_when_healthy(ctx):
    ctx.journal.add_account("FN", start_balance=100_000)
    assert risk_alerts(ctx) == []


def test_goal_alert_when_behind(ctx):
    ctx.goals.add("Notgroschen", target_value=10_000, start_value=0, current_value=100,
                  deadline=(date.today() + timedelta(days=2)).isoformat())
    titles = [a.title for a in goal_alerts(ctx)]
    assert any("hinter Plan" in t for t in titles)


def test_no_goal_alert_when_on_track(ctx):
    ctx.goals.add("laeuft", target_value=100, start_value=0, current_value=98,
                  deadline=(date.today() + timedelta(days=300)).isoformat())
    assert goal_alerts(ctx) == []


def test_collect_alerts_survives_a_broken_rule(ctx, monkeypatch):
    import jarvis.notify.center as center_mod

    def boom(_ctx):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(center_mod, "risk_alerts", boom)
    ctx.goals.add("hinterher", target_value=100, start_value=0, current_value=1,
                  deadline=(date.today() + timedelta(days=1)).isoformat())
    assert len(collect_alerts(ctx)) >= 1        # die anderen Regeln laufen weiter
