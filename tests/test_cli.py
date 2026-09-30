"""Die Kommandozeile: jeder Befehl muss zumindest sauber durchlaufen."""

import pytest

from jarvis import cli


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Jeder Test bekommt seinen eigenen Datenordner."""
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    from jarvis.storage import db as db_mod

    monkeypatch.setattr(db_mod, "_DB", None)
    yield


def run(*args: str) -> int:
    return cli.main(list(args))


def test_parser_knows_every_command():
    parser = cli.build_parser()
    action = next(a for a in parser._actions if a.dest == "command")
    assert {"chat", "brief", "task", "trade", "risk", "market", "goal", "sync",
            "notify", "app", "serve", "daemon", "doctor", "skills"} <= set(action.choices)


def test_every_subcommand_has_a_handler():
    """Ein vergessener Handler faellt hier auf, nicht erst beim Nutzer."""
    parser = cli.build_parser()
    action = next(a for a in parser._actions if a.dest == "command")
    for name, sub in action.choices.items():
        assert sub.get_default("func") is not None, f"{name} hat keine Funktion"


def test_doctor_runs(capsys):
    assert run("doctor") == 0
    assert "Werkzeuge" in capsys.readouterr().out


def test_skills_lists_every_tool(capsys):
    assert run("skills") == 0
    output = capsys.readouterr().out
    for name in ("task_add", "goal_add", "accounts_sync", "notify_send", "risk_check"):
        assert name in output


def test_task_flow(capsys):
    assert run("task", "add", "Steuer", "--due", "morgen", "--priority", "hoch") == 0
    assert run("task", "list") == 0
    assert "Steuer" in capsys.readouterr().out
    assert run("task", "done", "steuer") == 0


def test_goal_flow(capsys):
    assert run("goal", "add", "Payout", "--target", "108000", "--start", "100000",
               "--unit", "USD", "--deadline", "2026-12-31") == 0
    assert run("goal", "progress", "payout", "104000") == 0
    output = capsys.readouterr().out
    assert "50.0" in output or "50,0" in output


def test_account_and_risk_flow(capsys):
    assert run("account", "add", "--name", "FN", "--balance", "100000") == 0
    assert run("risk", "size", "--symbol", "EURUSD", "--entry", "1.0850",
               "--sl", "1.0820", "--risk", "0.5") == 0
    assert "1.67" in capsys.readouterr().out
    assert run("risk", "check") == 0


def test_trade_flow():
    run("account", "add", "--name", "FN", "--balance", "100000")
    assert run("trade", "log", "EURUSD", "long", "--entry", "1.0850", "--exit", "1.0910",
               "--sl", "1.0820", "--pnl", "600", "--account", "FN") == 0
    assert run("trade", "stats") == 0
    assert run("trade", "status") == 0


def test_sync_without_connector_is_not_an_error(capsys):
    run("account", "add", "--name", "FN", "--balance", "100000")
    assert run("sync") == 0
    assert "FUNDEDNEXT_TOKEN" in capsys.readouterr().out


def test_notify_check_without_channel():
    assert run("notify", "--check") == 0


def test_brief_runs_offline(capsys):
    assert run("brief", "--no-market", "--no-llm") == 0
    assert "#" in capsys.readouterr().out


def test_daemon_plan(capsys):
    assert run("daemon", "--once") == 0
    assert "morgen-briefing" in capsys.readouterr().out


def test_memory_flow(capsys):
    assert run("memory", "remember", "regel", "max", "0.5%", "pro", "Trade") == 0
    assert run("memory", "list") == 0
    assert "regel" in capsys.readouterr().out


def test_unknown_command_exits_with_usage():
    with pytest.raises(SystemExit):
        run("gibtsnicht")


def test_errors_become_exit_code_one():
    assert run("task", "done", "gibtsnicht") == 1
