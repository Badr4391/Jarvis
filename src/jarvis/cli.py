"""Kommandozeile: `jarvis <bereich> <aktion>`."""

from __future__ import annotations

import argparse
import sys

from jarvis import __version__
from jarvis import cli_util as out
from jarvis.config import Config, load_config
from jarvis.core.assistant import Assistant
from jarvis.core.context import JarvisContext

# --------------------------------------------------------------------- chat


def cmd_chat(ctx: JarvisContext, args: argparse.Namespace) -> int:
    assistant = Assistant(ctx=ctx, session=args.session)
    if args.text:
        turn = assistant.ask(" ".join(args.text))
        print(turn.text)
        if args.verbose and turn.tool_log:
            out.info("\n[benutzt: " + ", ".join(turn.actions()) + "]")
        return 0

    out.head(f"Jarvis {__version__} - Chat")
    out.info(f"Modell: {ctx.llm.name}/{ctx.llm.model}. Beenden mit 'exit'.\n")
    while True:
        try:
            line = input("du > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.lower() in ("exit", "quit", "q", ":q"):
            return 0
        if not line:
            continue
        turn = assistant.ask(line)
        print(f"\njarvis > {turn.text}\n")
        if args.verbose and turn.tool_log:
            out.info("[benutzt: " + ", ".join(turn.actions()) + "]\n")


def cmd_talk(ctx: JarvisContext, args: argparse.Namespace) -> int:
    from jarvis.voice.session import VoiceSession

    session = VoiceSession(Assistant(ctx=ctx, session=args.session))
    if args.check:
        out.dump(session.diagnose())
        return 0
    session.loop()
    return 0


# ------------------------------------------------------------------ briefing


def cmd_brief(ctx: JarvisContext, args: argparse.Namespace) -> int:
    from jarvis.briefing import builder, render

    brief = builder.build(
        ctx, include_market=not args.no_market, with_llm=not args.no_llm, save=True
    )
    print(brief.markdown)

    ctx.config.ensure_dirs()
    if args.html or args.open:
        path = ctx.config.briefing_dir / f"{brief.day}.html"
        path.write_text(render.to_html(brief.markdown, title=f"Briefing {brief.day}"),
                        encoding="utf-8")
        out.ok(f"HTML: {path}")
    if args.save_md:
        path = ctx.config.briefing_dir / f"{brief.day}.md"
        path.write_text(brief.markdown, encoding="utf-8")
        out.ok(f"Markdown: {path}")
    if args.speak:
        from jarvis.voice.tts import TTS

        text = builder.to_speech_text(brief.data)
        audio = ctx.config.audio_dir / f"brief-{brief.day}.wav"
        if TTS(ctx.config.voice).speak(text, keep=audio):
            out.ok(f"Vorgelesen, Audio: {audio}")
        else:
            out.warn("Keine Sprachausgabe verfuegbar (`jarvis talk --check`).")
    return 0


def cmd_review(ctx: JarvisContext, args: argparse.Namespace) -> int:
    from jarvis.skills.base import run_skill

    payload = run_skill(ctx, "evening_review", {})
    out.dump(payload.get("result", payload))
    return 0


# ---------------------------------------------------------------------- life


def cmd_task(ctx: JarvisContext, args: argparse.Namespace) -> int:
    life = ctx.life
    if args.action == "add":
        task = life.add_task(" ".join(args.title), due=args.due, priority=args.priority,
                             project=args.project or "", notes=args.notes or "")
        out.ok(f"[{task['id']}] {task['title']}" + (f" (faellig {task['due']})" if task["due"] else ""))
    elif args.action == "list":
        groups = life.today_tasks()
        for label, key in (("Ueberfaellig", "overdue"), ("Heute", "today"), ("Ohne Datum", "someday")):
            rows = groups[key]
            if rows:
                out.head(label)
                out.table(rows, ["id", "title", "due", "priority", "project"])
        if args.all:
            out.head("Alle offenen")
            out.table(life.list_tasks(limit=args.limit), ["id", "title", "due", "priority", "project"])
    elif args.action == "done":
        target = life.get_task(int(args.ref)) if str(args.ref).isdigit() else life.find_task(args.ref)
        if not target:
            out.error("Aufgabe nicht gefunden")
            return 1
        life.complete_task(target["id"])
        out.ok(f"Erledigt: {target['title']}")
    return 0


def cmd_habit(ctx: JarvisContext, args: argparse.Namespace) -> int:
    if args.action == "log":
        ctx.life.log_habit(args.name, done=not args.miss, note=args.note or "")
        out.ok(f"{args.name}: {'erledigt' if not args.miss else 'nicht geschafft'}")
    elif args.action == "add":
        ctx.life.add_habit(args.name, target_per_week=args.target)
        out.ok(f"Gewohnheit angelegt: {args.name}")
    out.table(ctx.life.habit_overview(), ["name", "done_today", "streak", "this_week", "target_per_week"])
    return 0


def cmd_note(ctx: JarvisContext, args: argparse.Namespace) -> int:
    if args.action == "add":
        note = ctx.life.add_note(" ".join(args.text), title=args.title or "", tags=args.tags or "")
        out.ok(f"Notiz [{note['id']}] gespeichert")
    else:
        out.table(ctx.life.search_notes(" ".join(args.text)), ["id", "title", "body", "tags", "created_at"])
    return 0


def cmd_journal(ctx: JarvisContext, args: argparse.Namespace) -> int:
    entry = ctx.life.add_journal(" ".join(args.text), mood=args.mood, energy=args.energy)
    out.ok(f"Eintrag [{entry['id']}] gespeichert")
    out.dump(ctx.life.mood_trend())
    return 0


# ------------------------------------------------------------------- trading


def cmd_account(ctx: JarvisContext, args: argparse.Namespace) -> int:
    if args.action == "add":
        account = ctx.journal.add_account(
            args.name, start_balance=args.balance, balance=args.balance, broker=args.broker or "",
            kind=args.kind, max_daily_loss_pct=args.daily_loss, max_total_loss_pct=args.total_loss,
            profit_target_pct=args.target, phase=args.phase or "", currency=args.currency,
        )
        out.ok(f"Konto {account['name']}: {account['balance']} {account['currency']}")
    elif args.action == "balance":
        account = ctx.journal.set_balance(args.name, args.balance)
        out.ok(f"Neuer Stand: {account['balance']} {account['currency']}" if account else "Konto nicht gefunden")
    out.table(ctx.journal.list_accounts(),
              ["id", "name", "broker", "kind", "phase", "start_balance", "balance", "currency"])
    return 0


def cmd_trade(ctx: JarvisContext, args: argparse.Namespace) -> int:
    journal = ctx.journal

    if args.action == "log":
        trade = journal.log_trade(
            symbol=args.symbol, direction=args.direction, entry=args.entry, exit=args.exit,
            stop_loss=args.sl, take_profit=args.tp, size=args.size, pnl=args.pnl or 0.0,
            fees=args.fees or 0.0, account=args.account, setup=args.setup or "",
            emotion=args.emotion or "", rating=args.rating, notes=args.notes or "",
            closed_at=args.closed_at or (None if args.open else _now_iso()),
        )
        out.ok(f"Trade [{trade['id']}] {trade['symbol']} {trade['direction']}"
               + (f", R = {trade['r_multiple']}" if trade.get("r_multiple") is not None else ""))
        guard = journal.guard(account=args.account)
        if guard:
            out.info(f"Wachhund: {guard.status()} - Spielraum {guard.room:.2f}")

    elif args.action == "close":
        trade = journal.close_trade(args.id, exit=args.exit, pnl=args.pnl or 0.0,
                                    fees=args.fees or 0.0, notes=args.notes or "",
                                    rating=args.rating)
        if not trade:
            out.error("Trade nicht gefunden")
            return 1
        out.ok(f"Geschlossen: {trade['symbol']} -> {trade['pnl']} (R {trade['r_multiple']})")

    elif args.action == "list":
        rows = journal.list_trades(account=args.account, symbol=args.symbol,
                                   limit=args.limit, open_only=args.open)
        out.table(rows, ["id", "opened_at", "symbol", "direction", "size", "entry", "exit",
                         "pnl", "r_multiple", "setup"])

    elif args.action == "import":
        from jarvis.trading.importers import import_csv

        summary = import_csv(journal, args.file, account=args.account)
        out.ok(f"{summary['imported']} importiert, {summary['skipped']} Duplikate uebersprungen "
               f"(von {summary['rows']} Zeilen)")

    elif args.action == "stats":
        stats = journal.stats(account=args.account, days=args.days)
        stats.pop("equity", None)
        out.head(f"Kennzahlen - Konto {stats['account']}"
                 + (f", letzte {args.days} Tage" if args.days else ""))
        out.table([
            {"Kennzahl": "Trades", "Wert": stats["trades"]},
            {"Kennzahl": "Trefferquote", "Wert": f"{stats['winrate']}%"},
            {"Kennzahl": "Netto", "Wert": stats["net_pnl"]},
            {"Kennzahl": "Profit-Faktor", "Wert": stats["profit_factor"]},
            {"Kennzahl": "Erwartungswert", "Wert": stats["expectancy"]},
            {"Kennzahl": "Durchschnitt R", "Wert": stats["avg_r"]},
            {"Kennzahl": "Payoff", "Wert": stats["payoff_ratio"]},
            {"Kennzahl": "Max Drawdown", "Wert": f"{stats['max_drawdown']['absolute']} "
                                                 f"({stats['max_drawdown']['percent']}%)"},
            {"Kennzahl": "Beste Serie", "Wert": stats["streaks"]["best_win_streak"]},
            {"Kennzahl": "Schlimmste Serie", "Wert": stats["streaks"]["worst_loss_streak"]},
        ], ["Kennzahl", "Wert"])

    elif args.action == "review":
        review = journal.weekly_review(account=args.account)
        for label, key in (("Diese Woche", "week"), ("30 Tage", "month")):
            block = review[key]
            out.head(label)
            out.info(f"{block['trades']} Trades | netto {block['net_pnl']} | "
                     f"{block['winrate']}% | PF {block['profit_factor']}")
        breakdown = review["breakdown"]
        for label, key in (("Nach Symbol", "symbol"), ("Nach Setup", "setup"),
                           ("Nach Wochentag", "weekday"), ("Nach Stunde", "hour")):
            if breakdown[key]:
                out.head(label)
                out.table(breakdown[key], ["key", "trades", "net_pnl", "winrate", "avg"])
        if breakdown["leaks"]:
            out.head("Lecks")
            out.bullets(breakdown["leaks"])

    elif args.action == "status":
        status = journal.daily_status(account=args.account)
        out.head(f"Trading-Status {status['day']}")
        if not status["account"]:
            out.warn("Kein Konto hinterlegt: `jarvis account add --name ... --balance ...`")
            return 0
        currency = status["currency"]
        out.info(f"Konto {status['account']}: {status['balance']} {currency}")
        out.info(f"Heute {out.money(status['realized_today'], currency)} | "
                 f"Gestern {out.money(status['realized_yesterday'], currency)}")
        if status["guard"]:
            guard = status["guard"]
            out.info(f"Wachhund: {guard['status']} - Spielraum {guard['room']} {currency}, "
                     f"bis Ziel {guard['target_remaining']} {currency}")
        if status["open_trades"]:
            out.head("Offene Trades")
            out.table(status["open_trades"], ["id", "symbol", "direction", "size", "entry", "stop_loss"])
    return 0


def cmd_risk(ctx: JarvisContext, args: argparse.Namespace) -> int:
    from jarvis.skills.base import run_skill

    if args.action == "size":
        payload = run_skill(ctx, "risk_position_size", {
            "symbol": args.symbol, "entry": args.entry, "stop_loss": args.sl,
            "risk_pct": args.risk, "account": args.account or "", "balance": args.balance,
            "quote_to_account_rate": args.rate,
        })
        if not payload["ok"]:
            out.error(payload["error"])
            return 1
        position = payload["result"]["position"]
        out.head(f"Positionsgroesse {position['symbol']}")
        out.info(f"Risiko: {position['risk_amount']} ({position['risk_pct']}%)")
        out.info(f"Stop: {position['stop_pips']} Pips | Wert je Pip/Lot: {position['value_per_point']}")
        out.ok(f"Groesse: {position['lots']} Lot ({position['units']} Einheiten)")
        if position["note"]:
            out.warn(position["note"])
        guard = payload["result"].get("wachhund")
        if guard:
            out.info(f"Wachhund: {guard['status']} - Spielraum {guard['room']}")

    elif args.action == "check":
        payload = run_skill(ctx, "risk_check", {"account": args.account or ""})
        if not payload["ok"] or "error" in payload.get("result", {}):
            out.error(payload.get("error") or payload["result"]["error"])
            return 1
        data = payload["result"]
        out.head(f"Wachhund {data['account']}: {data['status']}")
        out.info(f"Spielraum heute: {data['daily_room']} von {data['daily_loss_limit']}")
        out.info(f"Gesamtpuffer: {data['total_room']} von {data['total_loss_limit']}")
        out.info(f"Trades heute: {data['trades_heute']} (noch {data['trades_uebrig']} erlaubt)")
        out.info(f"Bis Gewinnziel: {data['target_remaining']}")
        (out.warn if data["status"] != "OK" else out.ok)(data["empfehlung"])

    elif args.action == "rr":
        payload = run_skill(ctx, "risk_reward",
                            {"entry": args.entry, "stop_loss": args.sl, "take_profit": args.tp})
        out.info(f"CRV {payload['result']['crv']} - {payload['result']['bewertung']}")
    return 0


# -------------------------------------------------------------------- market


def cmd_market(ctx: JarvisContext, args: argparse.Namespace) -> int:
    market = ctx.market

    if args.action == "quote":
        rows = market.snapshot(args.symbols or None)
        errors = [r for r in rows if r.get("error")]
        if errors:
            out.warn(errors[0]["error"])
        out.table([r for r in rows if not r.get("error")],
                  ["symbol", "price", "change_pct", "day_low", "day_high"])

    elif args.action == "analyse":
        try:
            idea = market.trade_idea(args.symbol)
        except Exception as exc:                                    # noqa: BLE001
            out.error(str(exc))
            return 1
        read = idea["read"]
        out.head(f"{read['symbol']} - {read['trend']} (Bias {read['bias']}, {read['strength']}/5)")
        out.info(f"Kurs {read['price']} | RSI {read['rsi14']} | ATR {read['atr14']} ({read['atr_pct']}%)")
        out.info(f"SMA 20/50/200: {read['sma20']} / {read['sma50']} / {read['sma200']}")
        out.info(f"Support: {read['support']}")
        out.info(f"Resistance: {read['resistance']}")
        if read["comments"]:
            out.bullets(read["comments"])
        levels = idea["levels"]
        if "error" not in levels:
            out.head("Rechnerischer Rahmen (kein Signal)")
            out.info(f"Entry {levels['entry']} | Stop {levels['stop_loss']} | "
                     f"Ziel {levels['take_profit']} (CRV {levels['rr']})")
        out.warn(idea["disclaimer"])

    elif args.action == "scan":
        rows = market.scan(args.symbols or None)
        if not rows:
            out.warn("Keine Daten - FMP_API_KEY gesetzt?")
        out.table(rows, ["symbol", "price", "trend", "bias", "strength", "rsi14", "atr_pct"])

    elif args.action == "calendar":
        events = market.economic_events(days=args.days, only_important=not args.all)
        if not events:
            out.warn("Keine Termine gefunden (oder kein API-Key).")
        out.table(events, ["date", "country", "event", "impact", "estimate", "previous"])

    elif args.action == "news":
        out.table(market.news(kind=args.kind, limit=args.limit), ["date", "site", "title"])

    elif args.action == "macro":
        data = market.macro_dashboard()
        if not data:
            out.warn("Keine Makrodaten verfuegbar.")
        out.table([{"Indikator": k, **v} for k, v in data.items()],
                  ["Indikator", "date", "value", "previous", "direction"])

    elif args.action == "watch":
        if args.symbols:
            for symbol in args.symbols:
                market.add_to_watchlist(symbol)
        if args.remove:
            for symbol in args.remove:
                market.remove_from_watchlist(symbol)
        out.info("Watchlist: " + ", ".join(market.watchlist()))
    return 0


# -------------------------------------------------------------------- memory


def cmd_memory(ctx: JarvisContext, args: argparse.Namespace) -> int:
    if args.action == "remember":
        entry = ctx.memory.remember(args.key, " ".join(args.value), category=args.category)
        out.ok(f"Gemerkt: {entry['key']} = {entry['value']}")
    elif args.action == "forget":
        out.ok("Geloescht" if ctx.memory.forget(args.key) else "Nichts gefunden")
    elif args.action == "search":
        out.table(ctx.memory.search(args.key), ["key", "value", "category", "updated_at"])
    else:
        out.table(ctx.memory.all(), ["key", "value", "category", "updated_at"])
    return 0


# -------------------------------------------------------------- system/setup


def cmd_serve(ctx: JarvisContext, args: argparse.Namespace) -> int:
    from jarvis.api.server import serve

    serve(ctx, host=args.host, port=args.port)
    return 0


def cmd_daemon(ctx: JarvisContext, args: argparse.Namespace) -> int:
    from jarvis.core.scheduler import build_default_scheduler

    scheduler = build_default_scheduler(ctx)
    if args.once:
        out.dump(scheduler.plan())
        return 0
    scheduler.run_forever()
    return 0


def cmd_doctor(ctx: JarvisContext, args: argparse.Namespace) -> int:
    from jarvis.skills.base import load_all
    from jarvis.voice.recorder import available_recorders
    from jarvis.voice.stt import STT
    from jarvis.voice.tts import TTS

    cfg = ctx.config
    out.head(f"Jarvis {__version__}")
    rows = [
        {"Bereich": "Datenordner", "Status": str(cfg.data_dir),
         "Hinweis": "vorhanden" if cfg.data_dir.exists() else "wird bei Bedarf angelegt"},
        {"Bereich": "Datenbank", "Status": str(cfg.db_path),
         "Hinweis": f"{cfg.db_path.stat().st_size // 1024} KB" if cfg.db_path.exists() else "noch leer"},
        {"Bereich": "Sprachmodell", "Status": f"{ctx.llm.name}/{ctx.llm.model}",
         "Hinweis": "bereit" if ctx.llm.name != "echo" else "kein Key - Offline-Modus"},
        {"Bereich": "Marktdaten", "Status": "FMP " + ("aktiv" if cfg.market.fmp_api_key else "fehlt"),
         "Hinweis": "FMP_API_KEY in .env" if not cfg.market.fmp_api_key else
                    f"{len(ctx.market.watchlist())} Symbole"},
        {"Bereich": "Sprachausgabe", "Status": TTS(cfg.voice).engine(),
         "Hinweis": "piper/espeak/say installieren" if TTS(cfg.voice).engine() == "none" else ""},
        {"Bereich": "Spracherkennung", "Status": STT(cfg.voice).engine(),
         "Hinweis": "whisper.cpp oder faster-whisper" if STT(cfg.voice).engine() == "none" else ""},
        {"Bereich": "Mikrofon", "Status": ", ".join(available_recorders()) or "keins",
         "Hinweis": "arecord/sox/ffmpeg" if not available_recorders() else ""},
        {"Bereich": "Werkzeuge", "Status": str(len(load_all())), "Hinweis": "Skills geladen"},
        {"Bereich": "Konten", "Status": str(len(ctx.journal.list_accounts())), "Hinweis": ""},
        {"Bereich": "Trades", "Status": str(len(ctx.journal.list_trades(limit=100000))), "Hinweis": ""},
    ]
    out.table(rows, ["Bereich", "Status", "Hinweis"])
    return 0


def cmd_init(ctx: JarvisContext, args: argparse.Namespace) -> int:
    """Kurzer Einrichtungsdialog - legt Konto, Regeln und Gewohnheiten an."""
    cfg = ctx.config
    cfg.ensure_dirs()
    out.head("Jarvis einrichten")

    def ask(prompt: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        try:
            answer = input(f"{prompt}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            return default
        return answer or default

    name = ask("Wie soll ich dich nennen?", cfg.user.name)
    ctx.memory.remember("name", name, category="person")

    goal = ask("Dein wichtigstes Ziel gerade")
    if goal:
        ctx.memory.remember("ziel_aktuell", goal, category="ziel", weight=2.0)

    if ask("Trading-Konto anlegen? (j/n)", "j").lower().startswith("j"):
        account = ask("Name des Kontos", "Hauptkonto")
        balance = float(ask("Startkapital", "100000") or 100000)
        daily = float(ask("Tagesverlustgrenze in %", "5") or 5)
        total = float(ask("Gesamtverlustgrenze in %", "10") or 10)
        target = float(ask("Gewinnziel in %", "8") or 8)
        ctx.journal.add_account(account, start_balance=balance, balance=balance,
                                max_daily_loss_pct=daily, max_total_loss_pct=total,
                                profit_target_pct=target)
        risk = ask("Risiko pro Trade in %", "0.5")
        trades = ask("Maximale Trades pro Tag", "3")
        ctx.memory.remember("risiko_regel", f"max {risk}% pro Trade, max {trades} Trades/Tag",
                            category="trading", weight=2.0)
        out.ok(f"Konto {account} angelegt.")

    habits = ask("Gewohnheiten (kommagetrennt)", "Sport, Chart-Review, Lesen")
    for habit in [h.strip() for h in habits.split(",") if h.strip()]:
        ctx.life.add_habit(habit)

    symbols = ask("Watchlist (kommagetrennt)", ", ".join(cfg.market.watchlist))
    for symbol in [s.strip() for s in symbols.split(",") if s.strip()]:
        ctx.market.add_to_watchlist(symbol)

    out.ok("Fertig. Naechste Schritte:")
    out.bullets([
        "jarvis brief            - dein erstes Briefing",
        "jarvis chat             - mit Jarvis reden",
        "jarvis doctor           - was noch fehlt",
        "jarvis daemon           - Briefing automatisch am Morgen",
    ])
    return 0


def cmd_skills(ctx: JarvisContext, args: argparse.Namespace) -> int:
    from jarvis.skills.base import load_all

    rows = [
        {"Werkzeug": skill.name, "Bereich": skill.category,
         "Beschreibung": skill.description.split("\n")[0][:70]}
        for skill in sorted(load_all().values(), key=lambda s: (s.category, s.name))
    ]
    out.table(rows, ["Bereich", "Werkzeug", "Beschreibung"], title=f"{len(rows)} Werkzeuge")
    return 0


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Jarvis - persoenlicher Assistent fuer Leben, Trading und Maerkte.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  jarvis brief --html\n"
            "  jarvis chat \"was steht heute an?\"\n"
            "  jarvis task add \"Steuer\" --due freitag --priority hoch\n"
            "  jarvis risk size --symbol EURUSD --entry 1.0850 --sl 1.0820 --risk 0.5\n"
            "  jarvis trade import export.csv --account FN-100k\n"
            "  jarvis market analyse XAUUSD\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"jarvis {__version__}")
    parser.add_argument("--config", help="Pfad zur YAML-Konfiguration")
    parser.add_argument("--json", action="store_true", help="Rohdaten als JSON ausgeben")
    sub = parser.add_subparsers(dest="command", required=True)

    # chat / talk
    chat = sub.add_parser("chat", help="Mit Jarvis reden (Text)")
    chat.add_argument("text", nargs="*")
    chat.add_argument("--session", default="default")
    chat.add_argument("-v", "--verbose", action="store_true")
    chat.set_defaults(func=cmd_chat)

    talk = sub.add_parser("talk", help="Sprachmodus (Mikrofon + Stimme)")
    talk.add_argument("--session", default="voice")
    talk.add_argument("--check", action="store_true", help="Nur pruefen, was verfuegbar ist")
    talk.set_defaults(func=cmd_talk)

    # briefing
    brief = sub.add_parser("brief", help="Morgen-Briefing erzeugen")
    brief.add_argument("--speak", action="store_true", help="Vorlesen")
    brief.add_argument("--html", action="store_true", help="Als HTML speichern")
    brief.add_argument("--open", action="store_true", help="HTML schreiben (Pfad ausgeben)")
    brief.add_argument("--save-md", action="store_true", help="Markdown speichern")
    brief.add_argument("--no-market", action="store_true", help="Ohne Marktdaten")
    brief.add_argument("--no-llm", action="store_true", help="Ohne persoenliche Einleitung")
    brief.set_defaults(func=cmd_brief)

    review = sub.add_parser("review", help="Abend-Rueckblick")
    review.set_defaults(func=cmd_review)

    # life
    task = sub.add_parser("task", help="Aufgaben")
    task_sub = task.add_subparsers(dest="action", required=True)
    task_add = task_sub.add_parser("add")
    task_add.add_argument("title", nargs="+")
    task_add.add_argument("--due")
    task_add.add_argument("--priority", default="normal")
    task_add.add_argument("--project")
    task_add.add_argument("--notes")
    task_list = task_sub.add_parser("list")
    task_list.add_argument("--all", action="store_true")
    task_list.add_argument("--limit", type=int, default=30)
    task_done = task_sub.add_parser("done")
    task_done.add_argument("ref", help="id oder Stichwort")
    task.set_defaults(func=cmd_task)

    habit = sub.add_parser("habit", help="Gewohnheiten")
    habit_sub = habit.add_subparsers(dest="action", required=True)
    habit_log = habit_sub.add_parser("log")
    habit_log.add_argument("name")
    habit_log.add_argument("--miss", action="store_true", help="Heute nicht geschafft")
    habit_log.add_argument("--note")
    habit_add = habit_sub.add_parser("add")
    habit_add.add_argument("name")
    habit_add.add_argument("--target", type=int, default=7)
    habit_sub.add_parser("list")
    habit.set_defaults(func=cmd_habit)

    note = sub.add_parser("note", help="Notizen")
    note_sub = note.add_subparsers(dest="action", required=True)
    note_add = note_sub.add_parser("add")
    note_add.add_argument("text", nargs="+")
    note_add.add_argument("--title")
    note_add.add_argument("--tags")
    note_find = note_sub.add_parser("find")
    note_find.add_argument("text", nargs="+")
    note.set_defaults(func=cmd_note)

    journal = sub.add_parser("journal", help="Tagebuch / Stimmung")
    journal.add_argument("text", nargs="+")
    journal.add_argument("--mood", type=int)
    journal.add_argument("--energy", type=int)
    journal.set_defaults(func=cmd_journal)

    # trading
    account = sub.add_parser("account", help="Handelskonten")
    account_sub = account.add_subparsers(dest="action", required=True)
    account_add = account_sub.add_parser("add")
    account_add.add_argument("--name", required=True)
    account_add.add_argument("--balance", type=float, required=True)
    account_add.add_argument("--broker")
    account_add.add_argument("--kind", default="prop", choices=["prop", "live", "demo"])
    account_add.add_argument("--currency", default="USD")
    account_add.add_argument("--daily-loss", type=float, default=5.0)
    account_add.add_argument("--total-loss", type=float, default=10.0)
    account_add.add_argument("--target", type=float, default=8.0)
    account_add.add_argument("--phase")
    account_balance = account_sub.add_parser("balance")
    account_balance.add_argument("name")
    account_balance.add_argument("balance", type=float)
    account_sub.add_parser("list")
    account.set_defaults(func=cmd_account)

    trade = sub.add_parser("trade", help="Trades und Journal")
    trade_sub = trade.add_subparsers(dest="action", required=True)
    trade_log = trade_sub.add_parser("log")
    trade_log.add_argument("symbol")
    trade_log.add_argument("direction", choices=["long", "short", "buy", "sell"])
    trade_log.add_argument("--entry", type=float)
    trade_log.add_argument("--exit", type=float)
    trade_log.add_argument("--sl", type=float)
    trade_log.add_argument("--tp", type=float)
    trade_log.add_argument("--size", type=float)
    trade_log.add_argument("--pnl", type=float)
    trade_log.add_argument("--fees", type=float)
    trade_log.add_argument("--account")
    trade_log.add_argument("--setup")
    trade_log.add_argument("--emotion")
    trade_log.add_argument("--rating", type=int, choices=[1, 2, 3, 4, 5])
    trade_log.add_argument("--notes")
    trade_log.add_argument("--closed-at")
    trade_log.add_argument("--open", action="store_true", help="Trade laeuft noch")
    trade_close = trade_sub.add_parser("close")
    trade_close.add_argument("id", type=int)
    trade_close.add_argument("--exit", type=float, required=True)
    trade_close.add_argument("--pnl", type=float, required=True)
    trade_close.add_argument("--fees", type=float)
    trade_close.add_argument("--notes")
    trade_close.add_argument("--rating", type=int)
    trade_list = trade_sub.add_parser("list")
    trade_list.add_argument("--account")
    trade_list.add_argument("--symbol")
    trade_list.add_argument("--limit", type=int, default=20)
    trade_list.add_argument("--open", action="store_true")
    trade_import = trade_sub.add_parser("import")
    trade_import.add_argument("file")
    trade_import.add_argument("--account")
    trade_stats = trade_sub.add_parser("stats")
    trade_stats.add_argument("--account")
    trade_stats.add_argument("--days", type=int)
    trade_review = trade_sub.add_parser("review")
    trade_review.add_argument("--account")
    trade_status = trade_sub.add_parser("status")
    trade_status.add_argument("--account")
    trade.set_defaults(func=cmd_trade)

    risk = sub.add_parser("risk", help="Risiko und Limits")
    risk_sub = risk.add_subparsers(dest="action", required=True)
    risk_size = risk_sub.add_parser("size")
    risk_size.add_argument("--symbol", required=True)
    risk_size.add_argument("--entry", type=float, required=True)
    risk_size.add_argument("--sl", type=float, required=True)
    risk_size.add_argument("--risk", type=float)
    risk_size.add_argument("--account")
    risk_size.add_argument("--balance", type=float)
    risk_size.add_argument("--rate", type=float,
                           help="Kurs Notierungs- zu Kontowaehrung (z.B. 0.0067 fuer JPY->USD)")
    risk_check = risk_sub.add_parser("check")
    risk_check.add_argument("--account")
    risk_rr = risk_sub.add_parser("rr")
    risk_rr.add_argument("--entry", type=float, required=True)
    risk_rr.add_argument("--sl", type=float, required=True)
    risk_rr.add_argument("--tp", type=float, required=True)
    risk.set_defaults(func=cmd_risk)

    # market
    market = sub.add_parser("market", help="Kurse, Analyse, Wirtschaftsdaten")
    market_sub = market.add_subparsers(dest="action", required=True)
    market_quote = market_sub.add_parser("quote")
    market_quote.add_argument("symbols", nargs="*")
    market_analyse = market_sub.add_parser("analyse")
    market_analyse.add_argument("symbol")
    market_scan = market_sub.add_parser("scan")
    market_scan.add_argument("symbols", nargs="*")
    market_cal = market_sub.add_parser("calendar")
    market_cal.add_argument("--days", type=int, default=1)
    market_cal.add_argument("--all", action="store_true", help="auch unwichtige Termine")
    market_news = market_sub.add_parser("news")
    market_news.add_argument("--kind", default="general",
                             choices=["general", "forex", "crypto", "stock"])
    market_news.add_argument("--limit", type=int, default=8)
    market_sub.add_parser("macro")
    market_watch = market_sub.add_parser("watch")
    market_watch.add_argument("symbols", nargs="*")
    market_watch.add_argument("--remove", nargs="*", default=[])
    market.set_defaults(func=cmd_market)

    # memory
    memory = sub.add_parser("memory", help="Was Jarvis ueber dich weiss")
    memory_sub = memory.add_subparsers(dest="action", required=True)
    memory_remember = memory_sub.add_parser("remember")
    memory_remember.add_argument("key")
    memory_remember.add_argument("value", nargs="+")
    memory_remember.add_argument("--category", default="general")
    memory_forget = memory_sub.add_parser("forget")
    memory_forget.add_argument("key")
    memory_search = memory_sub.add_parser("search")
    memory_search.add_argument("key")
    memory_sub.add_parser("list")
    memory.set_defaults(func=cmd_memory)

    # system
    serve = sub.add_parser("serve", help="Web-Dashboard starten")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=cmd_serve)

    daemon = sub.add_parser("daemon", help="Zeitplaner (Briefing, Rueckblick, Erinnerungen)")
    daemon.add_argument("--once", action="store_true", help="Nur den Plan zeigen")
    daemon.set_defaults(func=cmd_daemon)

    doctor = sub.add_parser("doctor", help="Was laeuft, was fehlt")
    doctor.set_defaults(func=cmd_doctor)

    init = sub.add_parser("init", help="Ersteinrichtung")
    init.set_defaults(func=cmd_init)

    skills = sub.add_parser("skills", help="Alle Werkzeuge auflisten")
    skills.set_defaults(func=cmd_skills)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config: Config = load_config(args.config)
    config.ensure_dirs()
    ctx = JarvisContext(config=config)
    try:
        return int(args.func(ctx, args) or 0)
    except KeyboardInterrupt:
        print()
        return 130
    except Exception as exc:                                        # noqa: BLE001
        out.error(f"{type(exc).__name__}: {exc}")
        if "--debug" in sys.argv:
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
