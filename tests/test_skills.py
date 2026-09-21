"""Skill-Registry, Argumentpruefung und Gedaechtnis."""


from jarvis.skills.base import load_all, result_to_text, run_skill, tool_specs


def test_all_skills_load():
    skills = load_all()
    assert len(skills) >= 30
    for name in ("task_add", "trade_log", "risk_check", "market_analyze", "morning_brief",
                 "memory_remember"):
        assert name in skills


def test_tool_specs_are_valid_json_schema():
    for spec in tool_specs():
        assert spec.name and spec.description
        assert spec.parameters["type"] == "object"
        for key in spec.parameters["required"]:
            assert key in spec.parameters["properties"], f"{spec.name}: {key} fehlt"


def test_categories_filter():
    names = {spec.name for spec in tool_specs(["trading"])}
    assert "trade_log" in names and "task_add" not in names


def test_unknown_skill_is_an_error(ctx):
    result = run_skill(ctx, "gibt_es_nicht", {})
    assert result["ok"] is False and "Unbekannt" in result["error"]


def test_missing_required_argument(ctx):
    result = run_skill(ctx, "task_add", {})
    assert result["ok"] is False and "title" in result["error"]


def test_string_numbers_are_coerced(ctx):
    ctx.journal.add_account("K", start_balance=10_000)
    result = run_skill(ctx, "risk_position_size",
                       {"symbol": "EURUSD", "entry": "1.0850", "stop_loss": "1,0820",
                        "risk_pct": "1"})
    assert result["ok"] is True
    assert result["result"]["position"]["stop_pips"] == 30.0


def test_exceptions_become_results(ctx):
    result = run_skill(ctx, "risk_position_size",
                       {"symbol": "EURUSD", "entry": 1.08, "stop_loss": 1.08})
    assert result["ok"] is False and "ValueError" in result["error"]


def test_skill_round_trip(ctx):
    assert run_skill(ctx, "task_add", {"title": "Testaufgabe", "due": "heute"})["ok"]
    listed = run_skill(ctx, "task_list", {})["result"]
    assert listed["heute"]["today"][0]["title"] == "Testaufgabe"


def test_result_to_text_handles_errors():
    assert result_to_text({"ok": False, "error": "kaputt"}).startswith("FEHLER")
    assert "hallo" in result_to_text({"ok": True, "result": "hallo"})


def test_memory_skills(ctx):
    run_skill(ctx, "memory_remember",
              {"key": "risiko_regel", "value": "0.5% pro Trade", "category": "trading"})
    found = run_skill(ctx, "memory_recall", {"query": "risiko"})["result"]
    assert found[0]["value"] == "0.5% pro Trade"
    assert "risiko_regel" in ctx.memory.context_block()
    assert run_skill(ctx, "memory_forget", {"key": "risiko_regel"})["result"]["geloescht"]


def test_market_skills_degrade_without_api_key(ctx):
    result = run_skill(ctx, "market_analyze", {"symbol": "EURUSD"})
    assert result["ok"] is True
    assert "error" in result["result"]          # sauberer Hinweis statt Absturz
