"""Financial Modeling Prep Client - Kurse, Wirtschaftsdaten, News."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from jarvis.util.http import HttpError, request_json


class MarketDataUnavailable(RuntimeError):
    """Kein API-Key oder Endpunkt nicht erreichbar."""


class FMPClient:
    """Duenner Wrapper. Versucht die 'stable' API, faellt auf v3 zurueck."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://financialmodelingprep.com",
        cache_ttl: int = 300,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.cache_ttl = cache_ttl

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------ core
    def get(self, path: str, **params: Any) -> Any:
        if not self.enabled:
            raise MarketDataUnavailable(
                "FMP_API_KEY fehlt - Marktdaten sind deaktiviert. "
                "Key auf financialmodelingprep.com holen und in .env eintragen."
            )
        params["apikey"] = self.api_key
        return request_json(
            f"{self.base_url}/{path.lstrip('/')}", params=params, cache_ttl=self.cache_ttl
        )

    def _try(self, candidates: list[tuple[str, dict[str, Any]]]) -> Any:
        """Mehrere Endpunkt-Varianten durchprobieren (stable vs. v3)."""
        last: Exception | None = None
        for path, params in candidates:
            try:
                data = self.get(path, **params)
            except (HttpError, MarketDataUnavailable) as exc:
                if isinstance(exc, MarketDataUnavailable):
                    raise
                last = exc
                continue
            if data not in (None, [], {}):
                return data
        if last:
            raise last
        return []

    # ----------------------------------------------------------------- kurse
    def quote(self, symbol: str) -> dict[str, Any]:
        data = self._try(
            [
                ("stable/quote", {"symbol": symbol}),
                (f"api/v3/quote/{symbol}", {}),
            ]
        )
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else {}

    def quotes(self, symbols: list[str]) -> list[dict[str, Any]]:
        out = []
        for symbol in symbols:
            try:
                quote = self.quote(symbol)
            except (HttpError, MarketDataUnavailable):
                continue
            if quote:
                out.append(quote)
        return out

    def history(self, symbol: str, *, days: int = 120) -> list[dict[str, Any]]:
        """Tageskerzen, aelteste zuerst."""
        start = (date.today() - timedelta(days=days * 2)).isoformat()
        data = self._try(
            [
                ("stable/historical-price-eod/full", {"symbol": symbol, "from": start}),
                (f"api/v3/historical-price-full/{symbol}", {"from": start}),
            ]
        )
        candles = data.get("historical", []) if isinstance(data, dict) else data
        candles = [c for c in (candles or []) if c.get("close") is not None]
        candles.sort(key=lambda c: str(c.get("date", "")))
        return candles[-days:]

    def intraday(self, symbol: str, *, interval: str = "1hour", limit: int = 120) -> list[dict[str, Any]]:
        data = self._try(
            [
                (f"stable/historical-chart/{interval}", {"symbol": symbol}),
                (f"api/v3/historical-chart/{interval}/{symbol}", {}),
            ]
        )
        candles = data if isinstance(data, list) else []
        candles.sort(key=lambda c: str(c.get("date", "")))
        return candles[-limit:]

    # -------------------------------------------------------- wirtschaftsdaten
    def economic_calendar(
        self, *, from_date: str | None = None, to_date: str | None = None
    ) -> list[dict[str, Any]]:
        today = date.today()
        params = {
            "from": from_date or today.isoformat(),
            "to": to_date or (today + timedelta(days=1)).isoformat(),
        }
        data = self._try(
            [
                ("stable/economic-calendar", params),
                ("api/v3/economic_calendar", params),
            ]
        )
        return data if isinstance(data, list) else []

    def economic_indicator(self, name: str, *, limit: int = 12) -> list[dict[str, Any]]:
        data = self._try(
            [
                ("stable/economic-indicators", {"name": name}),
                ("api/v4/economic", {"name": name}),
            ]
        )
        rows = data if isinstance(data, list) else []
        rows.sort(key=lambda r: str(r.get("date", "")), reverse=True)
        return rows[:limit]

    def treasury_rates(self) -> list[dict[str, Any]]:
        data = self._try([("stable/treasury-rates", {}), ("api/v4/treasury", {})])
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------ news
    def news(self, *, kind: str = "general", symbols: list[str] | None = None,
             limit: int = 10) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if symbols:
            params["symbols"] = ",".join(symbols)
        endpoints = {
            "general": [("stable/news/general-latest", params), ("api/v4/general_news", params)],
            "forex": [("stable/news/forex-latest", params), ("api/v4/forex_news", params)],
            "crypto": [("stable/news/crypto-latest", params), ("api/v4/crypto_news", params)],
            "stock": [("stable/news/stock-latest", params), ("api/v3/stock_news", params)],
        }
        data = self._try(endpoints.get(kind, endpoints["general"]))
        rows = data if isinstance(data, list) else []
        return rows[:limit]

    def market_hours(self, exchange: str = "NASDAQ") -> dict[str, Any]:
        data = self._try(
            [
                ("stable/exchange-market-hours", {"exchange": exchange}),
                ("api/v3/is-the-market-open", {}),
            ]
        )
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else {}
