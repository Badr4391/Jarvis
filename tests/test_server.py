"""Web-Dashboard: Routen, Token-Schutz, Fehlerverhalten."""

import json
import urllib.error
import urllib.request

import pytest

from jarvis.api.server import JarvisHandler, serve


@pytest.fixture()
def server(ctx):
    ctx.journal.add_account("FN", start_balance=100_000)
    ctx.life.add_task("Testaufgabe", due="heute")
    httpd = serve(ctx, host="127.0.0.1", port=0, block=False)
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    JarvisHandler.token = ""


def get(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read())


def post(url: str, payload: dict):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def test_dashboard_page_is_served(server):
    with urllib.request.urlopen(server + "/", timeout=10) as response:
        body = response.read().decode()
    assert response.status == 200
    assert "<title>Jarvis</title>" in body


def test_status_route(server):
    status = get(server + "/api/status")
    assert status["accounts"] == 1 and status["open_tasks"] == 1


def test_tasks_route(server):
    assert get(server + "/api/tasks")["today"][0]["title"] == "Testaufgabe"


def test_trading_route(server):
    assert get(server + "/api/trading")["guard"]["status"] == "OK"


def test_create_and_complete_task(server):
    created = post(server + "/api/task", {"title": "Neu", "due": "morgen"})
    assert created["title"] == "Neu"
    done = post(server + "/api/task/done", {"id": created["id"]})
    assert done["status"] == "done"


def test_habit_toggle(server):
    rows = post(server + "/api/habit", {"name": "Sport", "done": True})
    assert rows[0]["done_today"] is True


def test_tool_route(server):
    result = post(server + "/api/tool", {"name": "risk_check", "arguments": {}})
    assert result["ok"] and result["result"]["status"] == "OK"


def test_unknown_route_is_404(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(server + "/api/gibtsnicht")
    assert exc.value.code == 404


def test_chat_requires_message(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(server + "/api/chat", {})
    assert exc.value.code == 400


def test_token_protects_routes(ctx, monkeypatch):
    monkeypatch.setenv("JARVIS_WEB_TOKEN", "geheim")
    httpd = serve(ctx, host="127.0.0.1", port=0, block=False)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            get(base + "/api/status")
        assert exc.value.code == 401
        assert get(base + "/api/status?token=geheim")["version"]
    finally:
        httpd.shutdown()
        httpd.server_close()
        JarvisHandler.token = ""
