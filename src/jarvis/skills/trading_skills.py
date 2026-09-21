"""Werkzeuge fuers Trading: Journal, Kennzahlen, Risiko, Prop-Firm-Limits."""

from __future__ import annotations

from typing import Any

from jarvis.skills.base import skill
from jarvis.trading.risk import position_size, reward_risk

STR = {"type": "string"}
NUM = {"type": "number"}
INT = {"type": "integer"}


@skill(
    "account_add",
    "Handelskonto anlegen oder aktualisieren (Prop-Firm, Live oder Demo).",
    properties={
        "name": STR,
        "start_balance": NUM,
        "balance": NUM,
        "broker": STR,
        "kind": {**STR, "description": "prop | live | demo"},
        "currency": STR,
        "max_daily_loss_pct": {**NUM, "description": "Tagesverlustgrenze in Prozent, z.B. 5"},
        "max_total_loss_pct": {**NUM, "description": "Gesamtverlustgrenze in Prozent, z.B. 10"},
        "profit_target_pct": {**NUM, "description": "Gewinnziel in Prozent, z.B. 8"},
        "phase": {**STR, "description": "z.B. 'Phase 1' oder 'Funded'"},
    },
    required=["name", "start_balance"],
    category="trading",
)
def account_add(ctx, name: str, start_balance: float, **kwargs) -> dict[str, Any]:
    clean = {k: v for k, v in kwargs.items() if v is not None and v != ""}
    return ctx.journal.add_account(name, start_balance=start_balance, **clean)


@skill("account_list", "Alle aktiven Handelskonten mit Stand.", category="trading")
def account_list(ctx) -> list[dict[str, Any]]:
    return ctx.journal.list_accounts()


@skill(
    "trade_log",
    "Trade ins Journal schreiben. Fuer geschlossene Trades exit und pnl mitgeben.",
    properties={
        "symbol": STR,
        "direction": {**STR, "description": "long | short"},
        "entry": NUM, "exit": NUM, "stop_loss": NUM, "take_profit": NUM,
        "size": {**NUM, "description": "Lots bzw. Kontrakte"},
        "pnl": {**NUM, "description": "Ergebnis in Kontowaehrung"},
        "fees": NUM,
        "opened_at": {**STR, "description": "ISO-Zeit, sonst jetzt"},
        "closed_at": {**STR, "description": "ISO-Zeit, leer lassen wenn noch offen"},
        "account": STR,
        "setup": {**STR, "description": "Name der Strategie"},
        "emotion": {**STR, "description": "Wie hast du dich gefuehlt?"},
        "rating": {**INT, "description": "Ausfuehrungsqualitaet 1-5"},
        "notes": STR,
    },
    required=["symbol", "direction"],
    category="trading",
)
def trade_log(ctx, symbol: str, direction: str, **kwargs) -> dict[str, Any]:
    clean = {k: v for k, v in kwargs.items() if v is not None and v != ""}
    trade = ctx.journal.log_trade(symbol=symbol, direction=direction, **clean)
    guard = ctx.journal.guard(account=clean.get("account"))
    return {"trade": trade, "wachhund": guard.to_dict() if guard else None}


@skill(
    "trade_close",
    "Offenen Trade schliessen.",
    properties={"id": INT, "exit": NUM, "pnl": NUM, "fees": NUM, "notes": STR, "rating": INT},
    required=["id", "exit", "pnl"],
    category="trading",
)
def trade_close(ctx, id: int, exit: float, pnl: float, fees: float = 0.0,
                notes: str = "", rating: int | None = None) -> dict[str, Any]:
    return ctx.journal.close_trade(id, exit=exit, pnl=pnl, fees=fees, notes=notes, rating=rating) or {
        "error": "Trade nicht gefunden"
    }


@skill(
    "trade_list",
    "Trades auflisten.",
    properties={"account": STR, "symbol": STR, "limit": INT,
                "open_only": {"type": "boolean"}},
    category="trading",
)
def trade_list(ctx, account: str = "", symbol: str = "", limit: int = 20,
               open_only: bool = False) -> list[dict[str, Any]]:
    return ctx.journal.list_trades(
        account=account or None, symbol=symbol or None, limit=limit, open_only=open_only
    )


@skill(
    "trading_stats",
    "Kennzahlen des Journals: Trefferquote, Profit-Faktor, Erwartungswert, Drawdown, Serien.",
    properties={"account": STR, "days": {**INT, "description": "Zeitraum in Tagen, leer = alles"}},
    category="trading",
)
def trading_stats(ctx, account: str = "", days: int | None = None) -> dict[str, Any]:
    stats = ctx.journal.stats(account=account or None, days=days)
    stats.pop("equity", None)
    return stats


@skill(
    "trading_breakdown",
    "Wo verdienst du Geld und wo verlierst du es: nach Symbol, Setup, Wochentag, Uhrzeit - inklusive Leck-Analyse.",
    properties={"account": STR, "days": INT},
    category="trading",
)
def trading_breakdown(ctx, account: str = "", days: int = 90) -> dict[str, Any]:
    return ctx.journal.breakdown(account=account or None, days=days)


@skill(
    "trading_status",
    "Tagesstatus: Kontostand, heutiges Ergebnis, offene Trades, verbleibender Risikospielraum.",
    properties={"account": STR},
    category="trading",
)
def trading_status(ctx, account: str = "") -> dict[str, Any]:
    return ctx.journal.daily_status(account=account or None)


@skill(
    "risk_position_size",
    "Positionsgroesse berechnen: wie viele Lots fuer x Prozent Risiko bei diesem Stop.",
    properties={
        "symbol": STR, "entry": NUM, "stop_loss": NUM,
        "risk_pct": {**NUM, "description": "Risiko in Prozent des Kontos, z.B. 0.5"},
        "account": {**STR, "description": "Konto, sonst das erste aktive"},
        "balance": {**NUM, "description": "Kontostand, falls kein Konto hinterlegt"},
        "quote_to_account_rate": {**NUM, "description": "Kurs Notierungs- zu Kontowaehrung, z.B. 1/150 bei USDJPY auf USD-Konto"},
    },
    required=["symbol", "entry", "stop_loss"],
    category="trading",
)
def risk_position_size(ctx, symbol: str, entry: float, stop_loss: float,
                       risk_pct: float | None = None, account: str = "",
                       balance: float | None = None,
                       quote_to_account_rate: float | None = None) -> dict[str, Any]:
    acc = ctx.journal.get_account(account or None)
    balance = balance if balance is not None else (float(acc["balance"]) if acc else 10000.0)
    risk_pct = risk_pct if risk_pct is not None else ctx.config.trading.default_risk_pct

    guard = ctx.journal.guard(account=account or None)
    max_lots = None
    if guard:
        allowed = guard.max_risk_for_trade(
            risk_pct=risk_pct, trades_left=max(1, ctx.config.trading.max_trades_per_day)
        )
        if allowed < balance * (risk_pct / 100.0):
            risk_pct = round(allowed / balance * 100.0, 3) if balance else risk_pct

    sizing = position_size(
        symbol=symbol, balance=balance, risk_pct=max(risk_pct, 0.001), entry=entry,
        stop_loss=stop_loss, quote_to_account_rate=quote_to_account_rate,
        account_currency=(acc["currency"] if acc else "USD"), max_lots=max_lots,
    )
    return {
        "position": sizing.to_dict(),
        "wachhund": guard.to_dict() if guard else None,
        "hinweis": "Kein Rat zum Einstieg - nur die Groesse zu deinem Risiko.",
    }


@skill(
    "risk_check",
    "Prop-Firm-Wachhund: Darf heute noch gehandelt werden, wie viel Spielraum bleibt?",
    properties={"account": STR},
    category="trading",
)
def risk_check(ctx, account: str = "") -> dict[str, Any]:
    guard = ctx.journal.guard(account=account or None)
    if not guard:
        return {"error": "Kein Konto hinterlegt. Lege eins mit account_add an."}
    from datetime import date

    data = guard.to_dict()
    cfg = ctx.config.trading
    today = date.today().isoformat()
    trades_today = [
        t for t in ctx.journal.list_trades(account=account or None, limit=200)
        if str(t.get("opened_at", "")).startswith(today)
    ]
    data["trades_heute"] = len(trades_today)
    data["trades_uebrig"] = max(0, cfg.max_trades_per_day - len(trades_today))
    data["regeln"] = {
        "max_risiko_pro_trade_pct": cfg.default_risk_pct,
        "max_trades_pro_tag": cfg.max_trades_per_day,
        "max_risiko_pro_tag_pct": cfg.max_risk_per_day_pct,
    }
    if data["trades_uebrig"] == 0 and data["status"] != "STOP":
        data["status"] = "VORSICHT"
    data["empfehlung"] = {
        "STOP": "Heute nicht mehr handeln. Limit erreicht.",
        "VORSICHT": (
            "Tageskontingent aufgebraucht - Feierabend."
            if data["trades_uebrig"] == 0
            else "Nur noch ein A+ Setup mit halber Groesse."
        ),
        "OK": "Spielraum vorhanden - Regeln trotzdem einhalten.",
    }[data["status"]]
    return data


@skill(
    "risk_reward",
    "Chance-Risiko-Verhaeltnis eines geplanten Trades.",
    properties={"entry": NUM, "stop_loss": NUM, "take_profit": NUM},
    required=["entry", "stop_loss", "take_profit"],
    category="trading",
)
def risk_reward(ctx, entry: float, stop_loss: float, take_profit: float) -> dict[str, Any]:
    ratio = reward_risk(entry=entry, stop_loss=stop_loss, take_profit=take_profit)
    return {
        "crv": ratio,
        "bewertung": "gut" if ratio >= 2 else ("grenzwertig" if ratio >= 1.5 else "zu schlecht"),
    }


@skill(
    "trading_review",
    "Woechentliche Auswertung mit Lecks und konkreten Verbesserungen.",
    properties={"account": STR},
    category="trading",
)
def trading_review(ctx, account: str = "") -> dict[str, Any]:
    review = ctx.journal.weekly_review(account=account or None)
    review["week"].pop("equity", None)
    review["month"].pop("equity", None)
    return review
