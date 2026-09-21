"""Konfiguration, Datenbank und Zeitplaner."""

from datetime import datetime

from jarvis.config import load_config
from jarvis.core.scheduler import DailyJob, Scheduler
from jarvis.storage.db import Database


def test_env_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_USER_NAME", "Badr")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    config = load_config(env_file=tmp_path / "nichts.env")
    assert config.data_dir == tmp_path
    assert config.user.name == "Badr"
    assert config.llm.available is True


def test_secrets_are_masked(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-geheim")
    monkeypatch.setenv("FMP_API_KEY", "fmp-geheim")
    dumped = load_config(env_file=tmp_path / "nichts.env").to_dict()
    assert dumped["llm"]["api_key"] == "***"
    assert "geheim" not in str(dumped)


def test_dotenv_does_not_override_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("JARVIS_USER_NAME=AusDatei\n")
    monkeypatch.setenv("JARVIS_USER_NAME", "AusUmgebung")
    assert load_config(env_file=env_file).user.name == "AusUmgebung"


def test_database_roundtrip(tmp_path):
    db = Database(tmp_path / "x.db")
    row_id = db.insert("notes", {"body": "hallo", "created_at": "2026-01-01"})
    assert db.one("SELECT * FROM notes WHERE id = ?", (row_id,))["body"] == "hallo"
    db.update("notes", row_id, {"body": "neu"})
    assert db.one("SELECT body FROM notes WHERE id = ?", (row_id,))["body"] == "neu"
    db.delete("notes", row_id)
    assert db.query("SELECT * FROM notes") == []


def test_database_json_meta(tmp_path):
    db = Database(tmp_path / "x.db")
    db.set_json("state", {"a": 1})
    assert db.get_json("state") == {"a": 1}
    assert db.get_json("fehlt", "default") == "default"


def test_job_runs_once_per_day():
    runs = []
    scheduler = Scheduler(logger=lambda _: None)
    scheduler.add("brief", 7, 0, lambda: runs.append(1))

    assert scheduler.tick(datetime(2026, 9, 21, 6, 59)) == []
    assert scheduler.tick(datetime(2026, 9, 21, 7, 0)) == ["brief"]
    assert scheduler.tick(datetime(2026, 9, 21, 9, 0)) == []
    assert scheduler.tick(datetime(2026, 9, 22, 7, 5)) == ["brief"]
    assert len(runs) == 2


def test_missed_job_runs_later_same_day():
    runs = []
    scheduler = Scheduler(logger=lambda _: None)
    scheduler.add("brief", 7, 0, lambda: runs.append(1))
    # Rechner war um 7 Uhr aus, erst um 11 Uhr wieder an
    assert scheduler.tick(datetime(2026, 9, 21, 11, 0)) == ["brief"]


def test_weekday_only_job_skips_weekend():
    scheduler = Scheduler(logger=lambda _: None)
    scheduler.add("brief", 7, 0, lambda: None, weekdays_only=True)
    assert scheduler.tick(datetime(2026, 9, 19, 8, 0)) == []     # Samstag
    assert scheduler.tick(datetime(2026, 9, 21, 8, 0)) == ["brief"]


def test_failing_job_does_not_stop_scheduler():
    messages = []
    scheduler = Scheduler(logger=messages.append)

    def boom():
        raise RuntimeError("kaputt")

    scheduler.add("kaputt", 7, 0, boom)
    scheduler.add("gut", 7, 0, lambda: None)
    fired = scheduler.tick(datetime(2026, 9, 21, 8, 0))
    assert fired == ["gut"]
    assert any("kaputt" in m for m in messages)


def test_next_run_is_in_the_future():
    job = DailyJob(name="x", hour=7, minute=0, action=lambda: None)
    now = datetime(2026, 9, 21, 9, 0)
    assert job.next_run(now) > now
