"""Ziele: Fortschritt, Tempo, Richtung, Automatik."""

from datetime import date, timedelta

import pytest

from jarvis.life.goals import GoalManager
from jarvis.trading.journal import TradingJournal


@pytest.fixture()
def goals(db):
    return GoalManager(db)


def in_days(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def test_progress_counts_up(goals):
    goal = goals.add("Konto auf 108k", target_value=108_000, start_value=100_000,
                     current_value=104_000, unit="USD")
    assert goal["progress_pct"] == 50.0
    assert goal["remaining"] == 4_000.0
    assert goal["direction"] == "hoch"


def test_progress_counts_down(goals):
    """Abnehmen, Schulden tilgen: kleiner werden ist auch Fortschritt."""
    goal = goals.add("Auf 78 kg", target_value=78, start_value=88, current_value=83, unit="kg")
    assert goal["progress_pct"] == 50.0
    assert goal["remaining"] == 5.0
    assert goal["direction"] == "runter"


def test_remaining_never_goes_negative(goals):
    goal = goals.add("Auf 78 kg", target_value=78, start_value=88, current_value=75)
    assert goal["remaining"] == 0.0


def test_goal_completes_itself_at_target(goals):
    goal = goals.add("10 Trades journaln", target_value=10, start_value=0, unit="Trades")
    goals.log_progress(goal["id"], 7)
    assert goals.get(goal["id"])["status"] == "active"
    updated = goals.log_progress(goal["id"], 10)
    assert updated["status"] == "done"


def test_descending_goal_completes(goals):
    goal = goals.add("Auf 78 kg", target_value=78, start_value=88, current_value=88)
    assert goals.log_progress(goal["id"], 77.8)["status"] == "done"


def test_pace_ahead_and_behind(goals):
    ahead = goals.add("schnell", target_value=100, start_value=0, current_value=90,
                      deadline=in_days(30))
    behind = goals.add("langsam", target_value=100, start_value=0, current_value=2,
                       deadline=in_days(3))
    assert ahead["pace"] == "vor Plan"
    assert behind["pace"] == "hinter Plan"


def test_pace_overdue(goals):
    goal = goals.add("verpasst", target_value=100, start_value=0, current_value=10,
                     deadline=(date.today() - timedelta(days=2)).isoformat())
    assert goal["pace"] == "ueberfaellig"
    assert goal["days_left"] == -2


def test_per_day_needed(goals):
    goal = goals.add("sparen", target_value=1_000, start_value=0, current_value=500,
                     deadline=in_days(10))
    assert goal["per_day_needed"] == 50.0


def test_goal_without_target_has_no_progress(goals):
    goal = goals.add("Gitarre lernen")
    assert goal["progress_pct"] is None
    assert goal["pace"] == "unbekannt"


def test_deadline_accepts_natural_language(goals):
    goal = goals.add("kurzfristig", deadline="morgen")
    assert goal["deadline"] == (date.today() + timedelta(days=1)).isoformat()


def test_history_is_chronological(goals):
    goal = goals.add("sparen", target_value=100, start_value=0)
    for day, value in (("2026-01-01", 10), ("2026-01-05", 40), ("2026-01-09", 70)):
        goals.log_progress(goal["id"], value, day=day)
    assert [row["value"] for row in goals.history(goal["id"])] == [10, 40, 70]


def test_auto_goal_follows_account_balance(db, goals):
    journal = TradingJournal(db)
    journal.add_account("FN", start_balance=100_000)
    goal = goals.add("Payout", target_value=108_000, start_value=100_000,
                     account="FN", metric="balance")
    journal.set_balance("FN", 104_000)
    updated = goals.sync_auto_goals(journal)
    assert [g["title"] for g in updated] == ["Payout"]
    assert goals.get(goal["id"])["progress_pct"] == 50.0


def test_auto_goal_profit_metric(db, goals):
    journal = TradingJournal(db)
    journal.add_account("FN", start_balance=100_000)
    goals.add("8k Gewinn", target_value=8_000, start_value=0, account="FN", metric="profit")
    journal.set_balance("FN", 106_000)
    goals.sync_auto_goals(journal)
    assert goals.list()[0]["current_value"] == 6_000.0


def test_sync_is_quiet_when_nothing_changed(db, goals):
    journal = TradingJournal(db)
    journal.add_account("FN", start_balance=100_000)
    goals.add("Payout", target_value=108_000, start_value=100_000,
              current_value=100_000, account="FN", metric="balance")
    assert goals.sync_auto_goals(journal) == []


def test_overview_groups_by_urgency(goals):
    goals.add("hinterher", target_value=100, start_value=0, current_value=1, deadline=in_days(2))
    goals.add("laeuft", target_value=100, start_value=0, current_value=95, deadline=in_days(300))
    overview = goals.overview()
    assert overview["aktiv"] == 2
    assert [g["title"] for g in overview["hinter_plan"]] == ["hinterher"]
    assert [g["title"] for g in overview["bald_faellig"]] == ["hinterher"]


def test_find_by_keyword(goals):
    goals.add("FundedNext Payout", target_value=1)
    assert goals.find("payout")["title"] == "FundedNext Payout"
    assert goals.find("gibtsnicht") is None
