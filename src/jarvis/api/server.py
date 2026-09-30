"""Lokaler App-Server: liefert die PWA und ihre JSON-Schnittstelle.

Standardmaessig nur auf 127.0.0.1. Wer die App vom Handy aus erreichen will,
bindet an 0.0.0.0 und setzt JARVIS_WEB_TOKEN - ohne Token wird dann abgelehnt.
"""

from __future__ import annotations

import json
import mimetypes
import os
import queue
import threading
from collections.abc import Callable
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from jarvis import __version__

WEB_DIR = Path(__file__).parent / "web"
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class EventHub:
    """Verteilt Ereignisse an alle offenen App-Fenster (Server-Sent Events)."""

    def __init__(self) -> None:
        self._clients: list[queue.Queue[str]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[str]:
        channel: queue.Queue[str] = queue.Queue(maxsize=32)
        with self._lock:
            self._clients.append(channel)
        return channel

    def unsubscribe(self, channel: queue.Queue[str]) -> None:
        with self._lock:
            if channel in self._clients:
                self._clients.remove(channel)

    def publish(self, event: str, payload: Any = None) -> int:
        message = json.dumps({"event": event, "payload": payload}, default=str,
                             ensure_ascii=False)
        with self._lock:
            targets = list(self._clients)
        delivered = 0
        for channel in targets:
            try:
                channel.put_nowait(message)
                delivered += 1
            except queue.Full:
                continue
        return delivered

    @property
    def listeners(self) -> int:
        with self._lock:
            return len(self._clients)


HUB = EventHub()


def _json_default(value: Any) -> str:
    return str(value)


class JarvisHandler(BaseHTTPRequestHandler):
    ctx: Any = None
    token: str = ""
    server_version = f"Jarvis/{__version__}"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------- versand
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200,
                    extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status,
                         {"Cache-Control": "no-store"})

    def _static(self, name: str) -> bool:
        """Datei aus web/ ausliefern. Verhindert Ausbrueche aus dem Ordner."""
        target = (WEB_DIR / name).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            return False
        suffix = target.suffix.lower()
        content_type = STATIC_TYPES.get(suffix) or mimetypes.guess_type(target.name)[0] \
            or "application/octet-stream"
        # Der Service Worker darf nie aus dem Cache kommen, sonst haengt die App fest.
        cache = "no-cache" if target.name == "sw.js" else "public, max-age=300"
        self._send_bytes(target.read_bytes(), content_type, 200, {"Cache-Control": cache})
        return True

    # ---------------------------------------------------------------- auth
    def _authorized(self, query: dict[str, list[str]]) -> bool:
        if not self.token:
            return True
        supplied = (
            self.headers.get("X-Jarvis-Token", "")
            or (query.get("token") or [""])[0]
            or self._cookie_token()
        )
        return supplied == self.token

    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            key, _, value = part.strip().partition("=")
            if key == "jarvis_token":
                return value
        return ""

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------ GET
    def do_GET(self) -> None:                                   # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        route = parsed.path.rstrip("/") or "/"

        # Statisches darf ohne Token kommen - die Huelle enthaelt keine Daten.
        if route == "/":
            if not self._static("index.html"):
                self._send({"error": "index.html fehlt"}, 500)
            return
        if route.count("/") == 1 and (WEB_DIR / route.lstrip("/")).suffix:
            if self._static(route.lstrip("/")):
                return

        if not self._authorized(query):
            self._send({"error": "Token fehlt oder falsch"}, 401)
            return

        if route == "/api/stream":
            self._stream()
            return
        if route == "/api/brief.html":
            from jarvis.briefing import builder, render

            brief = builder.build(self.ctx, include_market=True, with_llm=False, save=True)
            self._send_bytes(
                render.to_html(brief.markdown, title=f"Briefing {brief.day}").encode("utf-8"),
                "text/html; charset=utf-8",
            )
            return

        handler = GET_ROUTES.get(route)
        if handler is None:
            self._send({"error": f"Unbekannter Pfad: {route}"}, 404)
            return
        try:
            self._send(handler(self.ctx, query))
        except Exception as exc:                                # noqa: BLE001
            self._send({"error": f"{type(exc).__name__}: {exc}"}, 500)

    # ------------------------------------------------------------------ SSE
    def _stream(self) -> None:
        """Offene Verbindung, ueber die der Server von sich aus melden kann."""
        channel = HUB.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self.wfile.write(b': verbunden\n\n')
            self.wfile.flush()
            while True:
                try:
                    message = channel.get(timeout=20)
                    self.wfile.write(f"data: {message}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")          # haelt Proxys wach
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            HUB.unsubscribe(channel)

    # ------------------------------------------------------------------ POST
    def do_POST(self) -> None:                                  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        route = parsed.path.rstrip("/")

        if not self._authorized(query):
            self._send({"error": "Token fehlt oder falsch"}, 401)
            return

        handler = POST_ROUTES.get(route)
        if handler is None:
            self._send({"error": f"Unbekannter Pfad: {route}"}, 404)
            return
        try:
            payload = self._body()
            result, status = handler(self.ctx, payload)
            self._send(result, status)
        except Exception as exc:                                # noqa: BLE001
            self._send({"error": f"{type(exc).__name__}: {exc}"}, 500)


# ---------------------------------------------------------------- GET-Routen


def _status(ctx, query) -> dict[str, Any]:
    return {
        "version": __version__,
        "name": ctx.config.user.name,
        "day": date.today().isoformat(),
        "llm": f"{ctx.llm.name}/{ctx.llm.model}",
        "llm_bereit": ctx.llm.name != "echo",
        "marktdaten": bool(ctx.config.market.fmp_api_key),
        "kanaele": ctx.notify.channels(),
        "ungelesen": ctx.notify.unread_count(),
        "konten": len(ctx.journal.list_accounts()),
        "offene_aufgaben": len(ctx.life.list_tasks(limit=1000)),
        "aktive_ziele": len(ctx.goals.list()),
        "zuhoerer": HUB.listeners,
    }


def _heute(ctx, query) -> dict[str, Any]:
    """Alles fuer den Startbildschirm in einem Aufruf - ein Roundtrip aufs Handy."""
    ctx.goals.sync_auto_goals(ctx.journal)
    trading = ctx.journal.daily_status()
    trading["week"].pop("equity", None)
    return {
        "status": _status(ctx, query),
        "aufgaben": ctx.life.today_tasks(),
        "termine": ctx.life.agenda(days=1),
        "gewohnheiten": ctx.life.habit_overview(),
        "trading": trading,
        "portfolio": ctx.sync.portfolio(),
        "ziele": ctx.goals.list()[:4],
        "stimmung": ctx.life.mood_trend(),
        "meldungen": ctx.notify.inbox(limit=5),
    }


def _markt(ctx, query) -> dict[str, Any]:
    return {
        "kurse": ctx.market.snapshot(),
        "kalender": ctx.market.economic_events(days=int((query.get("days") or ["2"])[0])),
        "nachrichten": ctx.market.news(limit=10),
        "makro": ctx.market.macro_dashboard(),
    }


def _ziele(ctx, query) -> dict[str, Any]:
    ctx.goals.sync_auto_goals(ctx.journal)
    overview = ctx.goals.overview()
    for goal in overview["ziele"]:
        goal["verlauf"] = ctx.goals.history(goal["id"], limit=30)
    return overview


def _trading(ctx, query) -> dict[str, Any]:
    stats = ctx.journal.stats(days=int(query["days"][0]) if query.get("days") else None)
    stats.pop("equity", None)
    return {
        "status": ctx.journal.daily_status(),
        "portfolio": ctx.sync.portfolio(),
        "kennzahlen": stats,
        "trades": ctx.journal.list_trades(limit=25),
        "auswertung": ctx.journal.breakdown(days=90),
    }


GET_ROUTES: dict[str, Callable[[Any, dict[str, list[str]]], Any]] = {
    "/api/status": _status,
    "/api/heute": _heute,
    "/api/markt": _markt,
    "/api/ziele": _ziele,
    "/api/trading": _trading,
    "/api/portfolio": lambda ctx, q: ctx.sync.portfolio(),
    "/api/tasks": lambda ctx, q: ctx.life.today_tasks(),
    "/api/habits": lambda ctx, q: ctx.life.habit_overview(),
    "/api/agenda": lambda ctx, q: ctx.life.agenda(days=int((q.get("days") or ["7"])[0])),
    "/api/trades": lambda ctx, q: ctx.journal.list_trades(
        limit=int((q.get("limit") or ["25"])[0])),
    "/api/market": lambda ctx, q: ctx.market.snapshot(),
    "/api/calendar": lambda ctx, q: ctx.market.economic_events(
        days=int((q.get("days") or ["1"])[0])),
    "/api/news": lambda ctx, q: ctx.market.news(limit=int((q.get("limit") or ["8"])[0])),
    "/api/memory": lambda ctx, q: ctx.memory.all(),
    "/api/notifications": lambda ctx, q: {
        "ungelesen": ctx.notify.unread_count(),
        "meldungen": ctx.notify.inbox(limit=int((q.get("limit") or ["30"])[0])),
        "kanaele": ctx.notify.channels(),
    },
    "/api/verlauf": lambda ctx, q: ctx.memory.history(
        session=(q.get("session") or ["app"])[0], limit=int((q.get("limit") or ["40"])[0])),
}


def _brief(ctx, query) -> dict[str, Any]:
    from jarvis.briefing import builder

    with_llm = (query.get("llm") or ["0"])[0] in ("1", "true", "ja")
    brief = builder.build(ctx, include_market=True, with_llm=with_llm, save=True)
    return {"day": brief.day, "markdown": brief.markdown, "data": brief.data}


GET_ROUTES["/api/brief"] = _brief


# --------------------------------------------------------------- POST-Routen


def _post_chat(ctx, payload) -> tuple[Any, int]:
    from jarvis.core.assistant import Assistant

    message = str(payload.get("message", "")).strip()
    if not message:
        return {"error": "message fehlt"}, 400
    turn = Assistant(ctx=ctx, session=str(payload.get("session", "app"))).ask(message)
    HUB.publish("chat", {"text": turn.text, "tools": turn.actions()})
    return {"text": turn.text, "tools": turn.actions()}, 200


def _post_tool(ctx, payload) -> tuple[Any, int]:
    from jarvis.skills.base import run_skill

    name = str(payload.get("name", ""))
    result = run_skill(ctx, name, payload.get("arguments") or {})
    HUB.publish("tool", {"name": name, "ok": result.get("ok")})
    return result, 200


def _post_task(ctx, payload) -> tuple[Any, int]:
    title = str(payload.get("title", "")).strip()
    if not title:
        return {"error": "title fehlt"}, 400
    task = ctx.life.add_task(title, due=payload.get("due"),
                             priority=payload.get("priority", "normal"),
                             project=payload.get("project", ""))
    HUB.publish("tasks")
    return task, 200


def _post_task_done(ctx, payload) -> tuple[Any, int]:
    task = ctx.life.complete_task(int(payload.get("id", 0)))
    HUB.publish("tasks")
    return task or {"error": "nicht gefunden"}, 200 if task else 404


def _post_habit(ctx, payload) -> tuple[Any, int]:
    ctx.life.log_habit(str(payload.get("name", "")), done=bool(payload.get("done", True)))
    HUB.publish("habits")
    return ctx.life.habit_overview(), 200


def _post_goal(ctx, payload) -> tuple[Any, int]:
    title = str(payload.get("title", "")).strip()
    if not title:
        return {"error": "title fehlt"}, 400
    clean = {k: v for k, v in payload.items() if k != "title" and v not in (None, "")}
    goal = ctx.goals.add(title, **clean)
    HUB.publish("goals")
    return goal, 200


def _post_goal_progress(ctx, payload) -> tuple[Any, int]:
    goal_id = int(payload.get("id", 0))
    if not goal_id or payload.get("value") is None:
        return {"error": "id und value noetig"}, 400
    goal = ctx.goals.log_progress(goal_id, float(payload["value"]),
                                  note=str(payload.get("note", "")))
    HUB.publish("goals")
    return goal or {"error": "nicht gefunden"}, 200 if goal else 404


def _post_sync(ctx, payload) -> tuple[Any, int]:
    result = ctx.sync.run()
    result["ziele_aktualisiert"] = [g["title"] for g in ctx.goals.sync_auto_goals(ctx.journal)]
    HUB.publish("portfolio", result)
    return result, 200


def _post_balance(ctx, payload) -> tuple[Any, int]:
    account = str(payload.get("account", ""))
    if not account or payload.get("balance") is None:
        return {"error": "account und balance noetig"}, 400
    updated = ctx.journal.set_balance(account, float(payload["balance"]))
    if not updated:
        return {"error": "Konto nicht gefunden"}, 404
    ctx.sync.record_balance(updated["id"], float(payload["balance"]), source="manual")
    ctx.goals.sync_auto_goals(ctx.journal)
    HUB.publish("portfolio")
    return updated, 200


def _post_trade(ctx, payload) -> tuple[Any, int]:
    symbol = str(payload.get("symbol", "")).strip()
    if not symbol:
        return {"error": "symbol fehlt"}, 400
    clean = {k: v for k, v in payload.items()
             if k not in ("symbol", "direction") and v not in (None, "")}
    trade = ctx.journal.log_trade(symbol=symbol,
                                  direction=str(payload.get("direction", "long")), **clean)
    HUB.publish("trades")
    return trade, 200


def _post_alerts(ctx, payload) -> tuple[Any, int]:
    from jarvis.notify.center import collect_alerts

    alerts = collect_alerts(ctx)
    if payload.get("send"):
        for alert in alerts:
            ctx.notify.push(alert, dedupe_hours=4)
    return {"anzahl": len(alerts), "meldungen": [a.to_dict() for a in alerts]}, 200


def _post_read(ctx, payload) -> tuple[Any, int]:
    count = ctx.notify.mark_read(payload.get("id"))
    return {"gelesen": count, "ungelesen": ctx.notify.unread_count()}, 200


def _post_journal(ctx, payload) -> tuple[Any, int]:
    text = str(payload.get("text", "")).strip()
    if not text:
        return {"error": "text fehlt"}, 400
    entry = ctx.life.add_journal(text, mood=payload.get("mood"), energy=payload.get("energy"))
    return {"eintrag": entry, "trend": ctx.life.mood_trend()}, 200


POST_ROUTES: dict[str, Callable[[Any, dict[str, Any]], tuple[Any, int]]] = {
    "/api/chat": _post_chat,
    "/api/tool": _post_tool,
    "/api/task": _post_task,
    "/api/task/done": _post_task_done,
    "/api/habit": _post_habit,
    "/api/goal": _post_goal,
    "/api/goal/progress": _post_goal_progress,
    "/api/sync": _post_sync,
    "/api/balance": _post_balance,
    "/api/trade": _post_trade,
    "/api/alerts": _post_alerts,
    "/api/notifications/read": _post_read,
    "/api/journal": _post_journal,
}


# -------------------------------------------------------------------- start


def serve(ctx: Any, *, host: str = "127.0.0.1", port: int = 8765,
          block: bool = True) -> ThreadingHTTPServer:
    JarvisHandler.ctx = ctx
    JarvisHandler.token = os.environ.get("JARVIS_WEB_TOKEN", "")

    exposed = host not in ("127.0.0.1", "localhost", "::1")
    if exposed and not JarvisHandler.token:
        raise SystemExit(
            "Abgelehnt: ohne JARVIS_WEB_TOKEN wuerde die App offen im Netz stehen.\n"
            "  JARVIS_WEB_TOKEN=$(python3 -c \"import secrets;print(secrets.token_urlsafe(24))\") "
            "jarvis serve --host 0.0.0.0"
        )

    httpd = ThreadingHTTPServer((host, port), JarvisHandler)
    httpd.daemon_threads = True
    if not block:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd

    url = f"http://{host}:{port}"
    if JarvisHandler.token:
        url += f"/?token={JarvisHandler.token}"
    print(f"Jarvis-App laeuft: {url}")
    if exposed:
        print("Vom Handy: dieselbe URL mit der IP dieses Rechners aufrufen,")
        print("dann im Browser-Menue 'Zum Startbildschirm hinzufuegen'.")
    print("Beenden mit Strg+C.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nApp beendet.")
    finally:
        httpd.server_close()
    return httpd


def broadcast(event: str, payload: Any = None) -> int:
    """Von aussen (Scheduler) ein Ereignis in offene App-Fenster schicken."""
    return HUB.publish(event, payload)
