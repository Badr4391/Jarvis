"""Marktservice: verbindet FMP-Daten, Analyse und Watchlist."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from jarvis.market.analysis import SymbolRead, analyze_candles, suggest_stop
from jarvis.market.fmp import FMPClient, MarketDataUnavailable
from jarvis.storage.db import Database
from jarvis.util.http import HttpError

HIGH_IMPACT = {"high", "hoch", "3"}

# Ereignisse, die fuer einen Daytrader wirklich zaehlen.
KEY_EVENTS = (
    "non farm", "nonfarm", "nfp", "cpi", "core cpi", "ppi", "fomc", "interest rate",
    "unemployment", "gdp", "pmi", "retail sales", "ecb", "fed", "powell", "lagarde",
)


@dataclass
class MarketService:
    db: Database
    client: FMPClient

    # ------------------------------------------------------------- watchlist
    def watchlist(self) -> list[str]:
        rows = self.db.query("SELECT symbol FROM watchlist ORDER BY id")
        return [r["symbol"] for r in rows]

    def add_to_watchlist(self, symbol: str, *, kind: str = "forex", note: str = "") -> str:
        symbol = symbol.strip().upper()
        self.db.execute(
            "INSERT INTO watchlist(symbol, kind, note) VALUES(?,?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET kind=excluded.kind, note=excluded.note",
            (symbol, kind, note),
        )
        return symbol

    def remove_from_watchlist(self, symbol: str) -> None:
        self.db.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.strip().upper(),))

    def seed_watchlist(self, symbols: list[str]) -> list[str]:
        if not self.watchlist():
            for symbol in symbols:
                self.add_to_watchlist(symbol)
        return self.watchlist()

    # ----------------------------------------------------------------- kurse
    def snapshot(self, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        """Kompakte Kursuebersicht - faellt bei Fehlern still auf leer zurueck."""
        symbols = symbols or self.watchlist()
        out: list[dict[str, Any]] = []
        for symbol in symbols:
            try:
                quote = self.client.quote(symbol)
            except (HttpError, MarketDataUnavailable) as exc:
                out.append({"symbol": symbol, "error": str(exc)[:120]})
                continue
            if not quote:
                continue
            out.append(
                {
                    "symbol": quote.get("symbol", symbol),
                    "name": quote.get("name", ""),
                    "price": quote.get("price"),
                    "change_pct": quote.get("changesPercentage", quote.get("changePercentage")),
                    "day_low": quote.get("dayLow"),
                    "day_high": quote.get("dayHigh"),
                    "volume": quote.get("volume"),
                }
            )
        return out

    def analyze(self, symbol: str, *, days: int = 220) -> SymbolRead:
        candles = self.client.history(symbol, days=days)
        if not candles:
            raise MarketDataUnavailable(f"Keine Historie fuer {symbol}")
        return analyze_candles(symbol, candles)

    def trade_idea(self, symbol: str, *, atr_multiple: float = 1.5) -> dict[str, Any]:
        """Struktur-Lesart plus konkreter Stop/Target-Vorschlag (keine Empfehlung)."""
        read = self.analyze(symbol)
        return {
            "read": read.to_dict(),
            "summary": read.summary(),
            "levels": suggest_stop(read, multiple=atr_multiple),
            "disclaimer": "Analyse, keine Anlageberatung - eigene Regeln pruefen.",
        }

    def scan(self, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        """Watchlist durchleuchten, nach Trendstaerke sortiert."""
        results = []
        for symbol in symbols or self.watchlist():
            try:
                read = self.analyze(symbol)
            except (ValueError, HttpError, MarketDataUnavailable):
                continue
            results.append(
                {
                    "symbol": read.symbol, "price": read.price, "trend": read.trend,
                    "bias": read.bias, "strength": read.strength, "rsi14": read.rsi14,
                    "atr_pct": read.atr_pct, "summary": read.summary(),
                }
            )
        return sorted(results, key=lambda r: r["strength"], reverse=True)

    # ------------------------------------------------------- wirtschaftsdaten
    def economic_events(
        self, *, days: int = 1, only_important: bool = True, countries: tuple[str, ...] = ("US", "EU", "DE", "GB")
    ) -> list[dict[str, Any]]:
        today = date.today()
        try:
            rows = self.client.economic_calendar(
                from_date=today.isoformat(), to_date=(today + timedelta(days=days)).isoformat()
            )
        except (HttpError, MarketDataUnavailable):
            return []

        events = []
        for row in rows:
            country = str(row.get("country", "")).upper()
            impact = str(row.get("impact", "")).lower()
            name = str(row.get("event", ""))
            important = impact in HIGH_IMPACT or any(k in name.lower() for k in KEY_EVENTS)
            if only_important and not important:
                continue
            if countries and country and not any(country.startswith(c) for c in countries):
                continue
            events.append(
                {
                    "date": row.get("date"),
                    "country": country,
                    "event": name,
                    "impact": impact or ("high" if important else ""),
                    "actual": row.get("actual"),
                    "previous": row.get("previous"),
                    "estimate": row.get("estimate", row.get("consensus")),
                }
            )
        return sorted(events, key=lambda e: str(e.get("date") or ""))

    def macro_dashboard(self, indicators: tuple[str, ...] = ("GDP", "CPI", "unemploymentRate",
                                                             "federalFunds")) -> dict[str, Any]:
        """Wenige, aussagekraeftige Makro-Reihen mit Richtungsangabe."""
        out: dict[str, Any] = {}
        for name in indicators:
            try:
                rows = self.client.economic_indicator(name, limit=4)
            except (HttpError, MarketDataUnavailable):
                continue
            if not rows:
                continue
            latest = rows[0]
            previous = rows[1] if len(rows) > 1 else None
            value = latest.get("value")
            prev_value = previous.get("value") if previous else None
            direction = ""
            if value is not None and prev_value is not None:
                direction = "steigend" if value > prev_value else ("fallend" if value < prev_value else "flach")
            out[name] = {
                "date": latest.get("date"), "value": value,
                "previous": prev_value, "direction": direction,
            }
        return out

    def news(self, *, kind: str = "general", limit: int = 6) -> list[dict[str, Any]]:
        try:
            rows = self.client.news(kind=kind, limit=limit)
        except (HttpError, MarketDataUnavailable):
            return []
        return [
            {
                "title": row.get("title", ""),
                "site": row.get("site", row.get("publisher", "")),
                "date": row.get("publishedDate", row.get("date")),
                "url": row.get("url", ""),
                "symbol": row.get("symbol", ""),
            }
            for row in rows
        ]
