"""Werkzeuge fuer Markt und Wirtschaft."""

from __future__ import annotations

from typing import Any

from jarvis.market.fmp import MarketDataUnavailable
from jarvis.skills.base import skill

STR = {"type": "string"}
INT = {"type": "integer"}
NUM = {"type": "number"}


@skill(
    "market_snapshot",
    "Aktuelle Kurse der Watchlist oder gewaehlter Symbole.",
    properties={"symbols": {"type": "array", "items": {"type": "string"},
                            "description": "z.B. ['EURUSD','XAUUSD']"}},
    category="market",
)
def market_snapshot(ctx, symbols: list[str] | None = None) -> list[dict[str, Any]]:
    return ctx.market.snapshot(symbols)


@skill(
    "market_analyze",
    "Technische Analyse eines Symbols: Trend, Bias, SMA, RSI, ATR, Support/Resistance.",
    properties={"symbol": STR},
    required=["symbol"],
    category="market",
)
def market_analyze(ctx, symbol: str) -> dict[str, Any]:
    try:
        return ctx.market.trade_idea(symbol)
    except (MarketDataUnavailable, ValueError) as exc:
        return {"error": str(exc)}


@skill(
    "market_scan",
    "Watchlist nach Trendstaerke durchsuchen - wo ist gerade Bewegung?",
    properties={"symbols": {"type": "array", "items": {"type": "string"}}},
    category="market",
)
def market_scan(ctx, symbols: list[str] | None = None) -> list[dict[str, Any]]:
    return ctx.market.scan(symbols)


@skill(
    "watchlist_add",
    "Symbol auf die Watchlist setzen.",
    properties={"symbol": STR, "kind": {**STR, "description": "forex | stock | crypto | index"},
                "note": STR},
    required=["symbol"],
    category="market",
)
def watchlist_add(ctx, symbol: str, kind: str = "forex", note: str = "") -> dict[str, Any]:
    ctx.market.add_to_watchlist(symbol, kind=kind, note=note)
    return {"watchlist": ctx.market.watchlist()}


@skill("watchlist_show", "Aktuelle Watchlist anzeigen.", category="market")
def watchlist_show(ctx) -> list[str]:
    return ctx.market.watchlist()


@skill(
    "economic_calendar",
    "Wichtige Wirtschaftstermine (NFP, CPI, FOMC, EZB ...) der naechsten Tage.",
    properties={"days": INT, "only_important": {"type": "boolean"}},
    category="market",
)
def economic_calendar(ctx, days: int = 1, only_important: bool = True) -> list[dict[str, Any]]:
    return ctx.market.economic_events(days=days, only_important=only_important)


@skill(
    "macro_overview",
    "Makro-Lage: Zinsen, Inflation, Arbeitsmarkt, Wachstum mit Richtung.",
    category="market",
)
def macro_overview(ctx) -> dict[str, Any]:
    return ctx.market.macro_dashboard()


@skill(
    "market_news",
    "Aktuelle Marktnachrichten.",
    properties={"kind": {**STR, "description": "general | forex | crypto | stock"}, "limit": INT},
    category="market",
)
def market_news(ctx, kind: str = "general", limit: int = 6) -> list[dict[str, Any]]:
    return ctx.market.news(kind=kind, limit=limit)
