"""Aufgaben, Gewohnheiten, Datumserkennung."""

from datetime import date, timedelta

import pytest

from jarvis.life.manager import LifeManager, parse_when


@pytest.fixture()
def life(db):
    return LifeManager(db)


def test_parse_relative_dates():
    today = date(2026, 9, 21)                     # ein Montag
    assert parse_when("heute", today=today) == "2026-09-21"
    assert parse_when("morgen", today=today) == "2026-09-22"
    assert parse_when("freitag", today=today) == "2026-09-25"
    assert parse_when("in 3 Tagen", today=today) == "2026-09-24"


def test_parse_explicit_dates():
    today = date(2026, 9, 21)
    assert parse_when("2026-12-24", today=today) == "2026-12-24"
    assert parse_when("24.12.", today=today) == "2026-12-24"
    assert parse_when("01.02.", today=today) == "2027-02-01"     # schon vorbei -> naechstes Jahr
    assert parse_when("quatsch", today=today) is None


def test_task_lifecycle(life):
    task = life.add_task("Steuer", due="morgen", priority="hoch")
    assert task["priority"] == 1
    assert life.list_tasks() and life.list_tasks()[0]["id"] == task["id"]
    life.complete_task(task["id"])
    assert life.list_tasks() == []
    assert life.get_task(task["id"])["status"] == "done"


def test_today_tasks_groups_overdue(life):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    life.add_task("Alt", due=yesterday)
    life.add_task("Heute", due="heute")
    life.add_task("Irgendwann")
    groups = life.today_tasks()
    assert [t["title"] for t in groups["overdue"]] == ["Alt"]
    assert [t["title"] for t in groups["today"]] == ["Heute"]
    assert [t["title"] for t in groups["someday"]] == ["Irgendwann"]


def test_find_task_by_keyword(life):
    life.add_task("Steuerunterlagen sortieren")
    assert life.find_task("steuer")["title"] == "Steuerunterlagen sortieren"


def test_habit_streak_counts_consecutive_days(life):
    habit = life.add_habit("Sport")
    today = date.today()
    for offset in range(3):
        life.log_habit("Sport", day=(today - timedelta(days=offset)).isoformat())
    assert life.habit_streak(habit["id"], today=today) == 3


def test_habit_streak_breaks_on_gap(life):
    habit = life.add_habit("Lesen")
    today = date.today()
    life.log_habit("Lesen", day=today.isoformat())
    life.log_habit("Lesen", day=(today - timedelta(days=2)).isoformat())
    assert life.habit_streak(habit["id"], today=today) == 1


def test_habit_log_creates_missing_habit(life):
    life.log_habit("Meditation")
    assert [h["name"] for h in life.habit_overview()] == ["Meditation"]


def test_notes_search(life):
    life.add_note("Idee: Backtest fuer London Breakout", tags="trading")
    assert life.search_notes("london")
    assert life.search_notes("trading")
    assert life.search_notes("nichts") == []


def test_mood_trend(life):
    life.add_journal("guter Tag", mood=8, energy=7)
    life.add_journal("mieser Tag", mood=4, energy=5)
    trend = life.mood_trend()
    assert trend["entries"] == 2 and trend["avg_mood"] == 6.0
