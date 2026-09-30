"""FundedNext: Kontostaende und Limits direkt aus dem Dashboard holen.

Die Feldnamen folgen der offiziellen Dashboard-API:
  /accounts          -> id, login, plan, balance, equity, status, breached
  /account-overview  -> objectives.daily_loss.daily_loss_till_now  (Rest-Tagespuffer in $)
                        objectives.overall_loss.max_loss_till_now   (Rest-Gesamtpuffer in $)
                        objectives.profit_target                    (Ziel)
                        account_details.initial_balance

Basis-URL und Pfade sind einstellbar, weil FundedNext sie gelegentlich aendert.
Das Token holst du dir aus dem eingeloggten Dashboard (DevTools -> Network ->
beliebiger API-Aufruf -> Header `Authorization: Bearer ...`) und legst es als
FUNDEDNEXT_TOKEN in die .env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from jarvis.connectors.base import AccountSnapshot, ConnectorError
from jarvis.util.http import HttpError, request_json

DEFAULT_BASE_URL = "https://api.fundednext.com/api/v1"


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _dig(payload: Any, *path: str) -> Any:
    """Verschachtelten Wert holen, ohne bei fehlenden Ebenen zu stolpern."""
    cursor = payload
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


@dataclass
class FundedNextConnector:
    """Liest aktive Konten samt Puffer. Scheitert mit klarer Meldung."""

    name: str = "fundednext"
    token: str = ""
    base_url: str = DEFAULT_BASE_URL
    accounts_path: str = "accounts"
    overview_path: str = "account-overview"     # leer = nur Kontostaende holen
    timeout: int = 30
    tabs: tuple[str, ...] = ("forex", "futures")
    _cache: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> FundedNextConnector:
        return cls(
            token=os.environ.get("FUNDEDNEXT_TOKEN", ""),
            base_url=os.environ.get("FUNDEDNEXT_API_URL", DEFAULT_BASE_URL).rstrip("/"),
        )

    def enabled(self) -> bool:
        return bool(self.token)

    # ------------------------------------------------------------------ http
    def _get(self, path: str, **params: Any) -> Any:
        if not self.enabled():
            raise ConnectorError(
                "FUNDEDNEXT_TOKEN fehlt. Token im eingeloggten Dashboard aus dem "
                "Authorization-Header kopieren und in die .env schreiben."
            )
        try:
            return request_json(
                f"{self.base_url}/{path.lstrip('/')}",
                params={k: v for k, v in params.items() if v is not None},
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
        except HttpError as exc:
            if exc.status in (401, 403):
                raise ConnectorError(
                    "FundedNext lehnt das Token ab (abgelaufen?). Neues Token aus dem "
                    "Dashboard holen und FUNDEDNEXT_TOKEN aktualisieren."
                ) from exc
            if exc.status == 404:
                raise ConnectorError(
                    f"Endpunkt {path} nicht gefunden. FUNDEDNEXT_API_URL pruefen - "
                    "FundedNext verschiebt die API gelegentlich."
                ) from exc
            raise ConnectorError(f"FundedNext antwortet nicht: {exc}") from exc
        except Exception as exc:                                    # noqa: BLE001
            raise ConnectorError(f"FundedNext nicht erreichbar: {exc}") from exc

    @staticmethod
    def _rows(payload: Any) -> list[dict[str, Any]]:
        """Die API verpackt Listen mal in 'data', mal in 'data.data'."""
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("data", "accounts", "result"):
                inner = payload.get(key)
                if isinstance(inner, list):
                    return [row for row in inner if isinstance(row, dict)]
                if isinstance(inner, dict):
                    for nested in ("data", "accounts"):
                        if isinstance(inner.get(nested), list):
                            return [r for r in inner[nested] if isinstance(r, dict)]
        return []

    # ----------------------------------------------------------------- abruf
    def fetch(self) -> list[AccountSnapshot]:
        snapshots: list[AccountSnapshot] = []
        seen: set[str] = set()

        for tab in self.tabs:
            try:
                payload = self._get(self.accounts_path, type="active", tab=tab, limit=20)
            except ConnectorError:
                if tab == self.tabs[0]:
                    raise
                continue                                    # Futures optional
            for row in self._rows(payload):
                snapshot = self._to_snapshot(row)
                if snapshot and snapshot.external_id not in seen:
                    seen.add(str(snapshot.external_id))
                    snapshots.append(snapshot)
        return snapshots

    def _to_snapshot(self, row: dict[str, Any]) -> AccountSnapshot | None:
        balance = _num(row.get("balance"))
        if balance is None:
            return None

        login = str(row.get("login") or "").strip()
        plan = str(row.get("plan") or row.get("plan_name") or "").strip()
        account_id = row.get("id")
        name = f"FN-{login}" if login else (plan or f"FundedNext-{account_id}")

        snapshot = AccountSnapshot(
            name=name,
            balance=balance,
            equity=_num(row.get("equity")),
            currency=str(row.get("currency") or "USD"),
            provider=self.name,
            external_id=str(account_id) if account_id is not None else login or None,
            login=login or None,
            phase=plan,
            broker="FundedNext",
            status="breached" if row.get("breached") else str(row.get("status") or "active"),
            raw=row,
        )
        self._enrich_with_overview(snapshot, account_id)
        return snapshot

    def _enrich_with_overview(self, snapshot: AccountSnapshot, account_id: Any) -> None:
        """Puffer und Ziele nachladen - scheitert leise, der Stand bleibt gueltig."""
        if account_id is None or not self.overview_path:
            return
        try:
            payload = self._get(self.overview_path, account_id=account_id)
        except ConnectorError:
            return

        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        objectives = data.get("objectives") if isinstance(data, dict) else None
        if isinstance(objectives, dict):
            snapshot.daily_loss_left = _num(_dig(objectives, "daily_loss", "daily_loss_till_now"))
            snapshot.total_loss_left = _num(_dig(objectives, "overall_loss", "max_loss_till_now"))
            snapshot.max_daily_loss_pct = _num(
                _dig(objectives, "daily_loss", "target_value_percentage"))
            snapshot.max_total_loss_pct = _num(
                _dig(objectives, "overall_loss", "target_value_percentage"))
            snapshot.profit_target_pct = _num(
                _dig(objectives, "profit_target", "target_value_percentage"))
            target = _num(_dig(objectives, "profit_target", "target_value"))
            if target is not None:
                snapshot.profit_target_left = round(max(0.0, target - snapshot.balance), 2)

        details = data.get("account_details") if isinstance(data, dict) else None
        if isinstance(details, dict):
            snapshot.start_balance = _num(details.get("initial_balance"))
            if details.get("breached"):
                snapshot.status = "breached"
