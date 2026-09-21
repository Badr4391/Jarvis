"""Lokales Web-Dashboard - stdlib http.server, kein Framework noetig.

Standardmaessig nur auf 127.0.0.1 erreichbar. Wer es im Heimnetz oeffnet,
sollte JARVIS_WEB_TOKEN setzen (dann ist ?token=... bzw. der Header Pflicht).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from jarvis import __version__

WEB_DIR = Path(__file__).parent / "web"


def _json_default(value: Any) -> str:
    return str(value)


class JarvisHandler(BaseHTTPRequestHandler):
    ctx: Any = None
    token: str = ""
    server_version = f"Jarvis/{__version__}"

    # ------------------------------------------------------------- utilities
    def log_message(self, fmt: str, *args: Any) -> None:       # leiser Server
        return

    def _send(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, text: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, query: dict[str, list[str]]) -> bool:
        if not self.token:
            return True
        supplied = self.headers.get("X-Jarvis-Token", "") or (query.get("token") or [""])[0]
        return supplied == self.token

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    # ------------------------------------------------------------------- GET
    def do_GET(self) -> None:                                   # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        route = parsed.path.rstrip("/") or "/"

        if not self._authorized(query):
            self._send({"error": "Token fehlt oder falsch"}, 401)
            return

        if route in ("/", "/index.html"):
            self._send_html((WEB_DIR / "index.html").read_text(encoding="utf-8"))
            return

        handlers = {
            "/api/status": self._status,
            "/api/brief": lambda q: self._brief(q),
            "/api/brief.html": None,       # Sonderfall unten
            "/api/tasks": lambda q: self.ctx.life.today_tasks(),
            "/api/habits": lambda q: self.ctx.life.habit_overview(),
            "/api/agenda": lambda q: self.ctx.life.agenda(days=int((q.get("days") or ["3"])[0])),
            "/api/trading": lambda q: self.ctx.journal.daily_status(),
            "/api/trades": lambda q: self.ctx.journal.list_trades(
                limit=int((q.get("limit") or ["25"])[0])),
            "/api/stats": lambda q: self.ctx.journal.stats(
                days=int(q["days"][0]) if q.get("days") else None),
            "/api/breakdown": lambda q: self.ctx.journal.breakdown(),
            "/api/market": lambda q: self.ctx.market.snapshot(),
            "/api/calendar": lambda q: self.ctx.market.economic_events(
                days=int((q.get("days") or ["1"])[0])),
            "/api/news": lambda q: self.ctx.market.news(limit=8),
            "/api/memory": lambda q: self.ctx.memory.all(),
        }

        if route == "/api/brief.html":
            from jarvis.briefing import builder, render

            brief = builder.build(self.ctx, include_market=True, with_llm=False, save=True)
            self._send_html(render.to_html(brief.markdown, title=f"Briefing {brief.day}"))
            return

        handler = handlers.get(route)
        if handler is None:
            self._send({"error": f"Unbekannter Pfad: {route}"}, 404)
            return
        try:
            self._send(handler(query))
        except Exception as exc:                                # noqa: BLE001
            self._send({"error": f"{type(exc).__name__}: {exc}"}, 500)

    # ------------------------------------------------------------------ POST
    def do_POST(self) -> None:                                  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        route = parsed.path.rstrip("/")

        if not self._authorized(query):
            self._send({"error": "Token fehlt oder falsch"}, 401)
            return

        payload = self._body()
        try:
            if route == "/api/chat":
                from jarvis.core.assistant import Assistant

                message = str(payload.get("message", "")).strip()
                if not message:
                    self._send({"error": "message fehlt"}, 400)
                    return
                turn = Assistant(ctx=self.ctx, session=payload.get("session", "web")).ask(message)
                self._send({"text": turn.text, "tools": turn.actions()})
                return

            if route == "/api/tool":
                from jarvis.skills.base import run_skill

                name = str(payload.get("name", ""))
                self._send(run_skill(self.ctx, name, payload.get("arguments") or {}))
                return

            if route == "/api/task":
                task = self.ctx.life.add_task(
                    str(payload.get("title", "")).strip(),
                    due=payload.get("due"), priority=payload.get("priority", "normal"),
                )
                self._send(task)
                return

            if route == "/api/task/done":
                task = self.ctx.life.complete_task(int(payload.get("id", 0)))
                self._send(task or {"error": "nicht gefunden"})
                return

            if route == "/api/habit":
                self.ctx.life.log_habit(str(payload.get("name", "")),
                                        done=bool(payload.get("done", True)))
                self._send(self.ctx.life.habit_overview())
                return

            self._send({"error": f"Unbekannter Pfad: {route}"}, 404)
        except Exception as exc:                                # noqa: BLE001
            self._send({"error": f"{type(exc).__name__}: {exc}"}, 500)

    # --------------------------------------------------------------- routen
    def _status(self, query: dict[str, list[str]]) -> dict[str, Any]:
        ctx = self.ctx
        return {
            "version": __version__,
            "name": ctx.config.user.name,
            "day": date.today().isoformat(),
            "llm": f"{ctx.llm.name}/{ctx.llm.model}",
            "market_data": bool(ctx.config.market.fmp_api_key),
            "accounts": len(ctx.journal.list_accounts()),
            "open_tasks": len(ctx.life.list_tasks(limit=1000)),
        }

    def _brief(self, query: dict[str, list[str]]) -> dict[str, Any]:
        from jarvis.briefing import builder

        with_llm = (query.get("llm") or ["0"])[0] in ("1", "true", "ja")
        brief = builder.build(self.ctx, include_market=True, with_llm=with_llm, save=True)
        return {"day": brief.day, "markdown": brief.markdown, "data": brief.data}


def serve(ctx: Any, *, host: str = "127.0.0.1", port: int = 8765,
          block: bool = True) -> ThreadingHTTPServer:
    """Startet das Dashboard. Gibt den Server zurueck (fuer Tests: block=False)."""
    JarvisHandler.ctx = ctx
    JarvisHandler.token = os.environ.get("JARVIS_WEB_TOKEN", "")

    httpd = ThreadingHTTPServer((host, port), JarvisHandler)
    url = f"http://{host}:{port}"
    if JarvisHandler.token:
        url += f"/?token={JarvisHandler.token}"

    if not block:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd

    print(f"Jarvis-Dashboard laeuft: {url}")
    if host not in ("127.0.0.1", "localhost") and not JarvisHandler.token:
        print("WARNUNG: erreichbar im Netzwerk ohne Token. JARVIS_WEB_TOKEN setzen!")
    print("Beenden mit Strg+C.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard beendet.")
    finally:
        httpd.server_close()
    return httpd
