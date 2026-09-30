"""Die App-Schnittstelle: Routen, Statik, Token, Ereignisstrom."""

import json
import urllib.error
import urllib.request
from datetime import date

import pytest

from jarvis.api.server import HUB, JarvisHandler, broadcast, serve


@pytest.fixture()
def app(ctx):
    ctx.journal.add_account("FN-512345", start_balance=100_000, broker="FundedNext")
    ctx.life.add_task("Testaufgabe", due="heute")
    ctx.life.add_habit("Sport")
    ctx.goals.add("Payout", target_value=108_000, start_value=100_000, unit="USD",
                  account="FN-512345", metric="balance")
    httpd = serve(ctx, host="127.0.0.1", port=0, block=False)
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    JarvisHandler.token = ""


def get(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read())


def raw(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.headers["Content-Type"], response.read()


def post(url: str, payload: dict):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


# ------------------------------------------------------------------ statik


@pytest.mark.parametrize("path,expected", [
    ("/", "text/html"),
    ("/app.css", "text/css"),
    ("/app.js", "application/javascript"),
    ("/manifest.webmanifest", "application/manifest+json"),
    ("/sw.js", "application/javascript"),
    ("/icon.svg", "image/svg+xml"),
    ("/icon-192.png", "image/png"),
])
def test_static_files_are_served(app, path, expected):
    status, content_type, body = raw(app + path)
    assert status == 200
    assert content_type.startswith(expected)
    assert len(body) > 100


def test_app_shell_is_the_pwa(app):
    _, _, body = raw(app + "/")
    html = body.decode()
    assert 'rel="manifest"' in html
    assert 'id="page-ziele"' in html
    assert "<title>Jarvis</title>" in html


def test_manifest_is_installable(app):
    manifest = get(app + "/manifest.webmanifest")
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])
    assert any(icon["sizes"] == "512x512" for icon in manifest["icons"])


def test_service_worker_is_never_cached(app):
    with urllib.request.urlopen(app + "/sw.js", timeout=10) as response:
        assert response.headers["Cache-Control"] == "no-cache"


def test_directory_traversal_is_refused(app):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(app + "/../../etc/passwd")
    assert exc.value.code in (400, 404)


# ------------------------------------------------------------------ routen


def test_status_route(app):
    status = get(app + "/api/status")
    assert status["konten"] == 1
    assert status["offene_aufgaben"] == 1
    assert status["aktive_ziele"] == 1
    assert status["day"] == date.today().isoformat()
    assert "llm" in status and "kanaele" in status


def test_chat_needs_a_message(app):
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(app + "/api/chat", {"message": "   "})
    assert exc.value.code == 400


def test_heute_delivers_the_whole_screen_in_one_call(app):
    data = get(app + "/api/heute")
    for key in ("status", "aufgaben", "gewohnheiten", "trading", "portfolio", "ziele"):
        assert key in data
    assert data["status"]["day"] == date.today().isoformat()
    assert data["portfolio"]["gesamt"] == 100_000.0


def test_ziele_route_includes_history(app):
    data = get(app + "/api/ziele")
    assert data["ziele"][0]["title"] == "Payout"
    assert "verlauf" in data["ziele"][0]


def test_trading_route(app):
    data = get(app + "/api/trading?days=30")
    assert data["status"]["account"] == "FN-512345"
    assert "kennzahlen" in data and "auswertung" in data


def test_portfolio_route(app):
    assert get(app + "/api/portfolio")["konten"][0]["name"] == "FN-512345"


def test_task_create_and_complete(app):
    created = post(app + "/api/task", {"title": "Neu", "due": "morgen"})
    assert created["title"] == "Neu"
    assert post(app + "/api/task/done", {"id": created["id"]})["status"] == "done"


def test_goal_create_and_progress(app):
    goal = post(app + "/api/goal", {"title": "Sparen", "target_value": 1000,
                                     "start_value": 0, "unit": "EUR"})
    updated = post(app + "/api/goal/progress", {"id": goal["id"], "value": 250})
    assert updated["progress_pct"] == 25.0


def test_balance_update_moves_the_goal(app):
    post(app + "/api/balance", {"account": "FN-512345", "balance": 104_000})
    assert get(app + "/api/ziele")["ziele"][0]["progress_pct"] == 50.0


def test_sync_without_connector_reports_cleanly(app):
    result = post(app + "/api/sync", {})
    assert result["konten"] == []
    assert result["fehler"]


def test_habit_toggle(app):
    assert post(app + "/api/habit", {"name": "Sport", "done": True})[0]["done_today"] is True


def test_notifications_roundtrip(app):
    post(app + "/api/alerts", {"send": False})
    data = get(app + "/api/notifications")
    assert "meldungen" in data and "ungelesen" in data
    assert post(app + "/api/notifications/read", {})["ungelesen"] == 0


def test_journal_entry(app):
    result = post(app + "/api/journal", {"text": "guter Tag", "mood": 8})
    assert result["trend"]["entries"] == 1


def test_tool_route_runs_a_skill(app):
    result = post(app + "/api/tool", {"name": "risk_check", "arguments": {}})
    assert result["ok"] and result["result"]["status"] == "OK"


def test_missing_fields_are_rejected(app):
    for path, payload in (("/api/task", {}), ("/api/goal", {}), ("/api/chat", {})):
        with pytest.raises(urllib.error.HTTPError) as exc:
            post(app + path, payload)
        assert exc.value.code == 400


def test_unknown_route_is_404(app):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(app + "/api/gibtsnicht")
    assert exc.value.code == 404


# ------------------------------------------------------------------- token


def test_token_guards_data_but_not_the_shell(ctx, monkeypatch):
    monkeypatch.setenv("JARVIS_WEB_TOKEN", "geheim")
    httpd = serve(ctx, host="127.0.0.1", port=0, block=False)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert raw(base + "/")[0] == 200                  # Huelle ohne Daten ist frei
        with pytest.raises(urllib.error.HTTPError) as exc:
            get(base + "/api/status")
        assert exc.value.code == 401
        assert get(base + "/api/status?token=geheim")["version"]
    finally:
        httpd.shutdown()
        httpd.server_close()
        JarvisHandler.token = ""


def test_open_binding_without_token_is_refused(ctx):
    with pytest.raises(SystemExit, match="JARVIS_WEB_TOKEN"):
        serve(ctx, host="0.0.0.0", port=0, block=False)


# ------------------------------------------------------------ ereignisstrom


def test_hub_delivers_to_subscribers():
    channel = HUB.subscribe()
    try:
        assert broadcast("alert", {"title": "STOP"}) == 1
        message = json.loads(channel.get(timeout=2))
        assert message["event"] == "alert"
        assert message["payload"]["title"] == "STOP"
    finally:
        HUB.unsubscribe(channel)


def test_hub_forgets_closed_clients():
    channel = HUB.subscribe()
    HUB.unsubscribe(channel)
    assert HUB.listeners == 0
