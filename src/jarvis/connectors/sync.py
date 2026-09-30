"""Kontostaende einsammeln und ins Journal schreiben."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from jarvis.connectors.base import AccountConnector, AccountSnapshot, ConnectorError
from jarvis.storage.db import Database, utcnow


def build_connectors() -> list[AccountConnector]:
    """Alle eingerichteten Anbindungen. Nicht konfigurierte bleiben aussen vor."""
    from jarvis.connectors.fundednext import FundedNextConnector

    candidates: list[AccountConnector] = [FundedNextConnector.from_env()]
    return [c for c in candidates if c.enabled()]


@dataclass
class AccountSync:
    db: Database
    journal: Any

    # -------------------------------------------------------------- schreiben
    def apply(self, snapshot: AccountSnapshot) -> dict[str, Any]:
        """Einen gemeldeten Stand uebernehmen - vorhandenes Konto wird erkannt."""
        existing = None
        if snapshot.external_id:
            existing = self.db.one(
                "SELECT * FROM accounts WHERE provider = ? AND external_id = ?",
                (snapshot.provider, snapshot.external_id),
            )
        if not existing:
            existing = self.db.one(
                "SELECT * FROM accounts WHERE lower(name) = ?", (snapshot.name.lower(),)
            )

        values: dict[str, Any] = {
            "balance": snapshot.balance,
            "equity": snapshot.equity,
            "provider": snapshot.provider,
            "external_id": snapshot.external_id,
            "login": snapshot.login,
            "synced_at": utcnow(),
            "active": 0 if snapshot.status == "breached" else 1,
        }
        for column, value in (
            ("currency", snapshot.currency),
            ("phase", snapshot.phase),
            ("broker", snapshot.broker),
            ("max_daily_loss_pct", snapshot.max_daily_loss_pct),
            ("max_total_loss_pct", snapshot.max_total_loss_pct),
            ("profit_target_pct", snapshot.profit_target_pct),
        ):
            if value not in (None, ""):
                values[column] = value

        if existing:
            if snapshot.start_balance is not None:
                values["start_balance"] = snapshot.start_balance
            self.db.update("accounts", existing["id"], values)
            account_id = existing["id"]
            created = False
        else:
            account_id = self.db.insert(
                "accounts",
                {
                    "name": snapshot.name,
                    "kind": "prop" if snapshot.provider != "manual" else "live",
                    "start_balance": snapshot.start_balance
                    if snapshot.start_balance is not None else snapshot.balance,
                    "created_at": utcnow(),
                    "max_daily_loss_pct": snapshot.max_daily_loss_pct or 5.0,
                    "max_total_loss_pct": snapshot.max_total_loss_pct or 10.0,
                    "profit_target_pct": snapshot.profit_target_pct or 8.0,
                    **values,
                },
            )
            created = True

        self.record_balance(account_id, snapshot.balance, equity=snapshot.equity,
                            source=snapshot.provider)
        return {"account_id": account_id, "name": snapshot.name,
                "balance": snapshot.balance, "neu": created}

    def record_balance(self, account_id: int, balance: float, *, equity: float | None = None,
                       source: str = "manual", day: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO balance_history(account_id, day, balance, equity, source, created_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(account_id, day) DO UPDATE SET "
            "balance=excluded.balance, equity=excluded.equity, source=excluded.source, "
            "created_at=excluded.created_at",
            (account_id, day or date.today().isoformat(), balance, equity, source, utcnow()),
        )

    # ------------------------------------------------------------------ lauf
    def run(self, connectors: list[AccountConnector] | None = None) -> dict[str, Any]:
        """Alle Anbindungen abfragen. Fehler werden gesammelt, nicht geworfen."""
        connectors = connectors if connectors is not None else build_connectors()
        applied: list[dict[str, Any]] = []
        errors: list[str] = []

        for connector in connectors:
            try:
                for snapshot in connector.fetch():
                    applied.append(self.apply(snapshot))
            except ConnectorError as exc:
                errors.append(f"{connector.name}: {exc}")
            except Exception as exc:                               # noqa: BLE001
                errors.append(f"{connector.name}: {type(exc).__name__}: {exc}")

        if not connectors and not errors:
            errors.append(
                "Keine Anbindung eingerichtet. FUNDEDNEXT_TOKEN setzen oder Stand "
                "manuell pflegen: jarvis account balance <name> <betrag>"
            )
        return {
            "zeitpunkt": utcnow(),
            "konten": applied,
            "fehler": errors,
            "anbindungen": [c.name for c in connectors],
        }

    # ----------------------------------------------------------------- lesen
    def equity_curve(self, account_id: int, *, days: int = 90) -> list[dict[str, Any]]:
        return self.db.query(
            "SELECT day, balance, equity FROM balance_history WHERE account_id = ? "
            "ORDER BY day DESC LIMIT ?",
            (account_id, days),
        )[::-1]

    def portfolio(self) -> dict[str, Any]:
        """Alle Konten auf einen Blick - die Zahl, die aufs Handy gehoert."""
        accounts = self.journal.list_accounts()
        rows = []
        total = 0.0
        total_start = 0.0
        for account in accounts:
            guard = self.journal.guard(account=account["id"])
            balance = float(account["balance"])
            start = float(account["start_balance"])
            total += balance
            total_start += start
            rows.append(
                {
                    "id": account["id"],
                    "name": account["name"],
                    "broker": account["broker"],
                    "phase": account["phase"],
                    "currency": account["currency"],
                    "balance": round(balance, 2),
                    "equity": account.get("equity"),
                    "start_balance": round(start, 2),
                    "pnl": round(balance - start, 2),
                    "pnl_pct": round((balance - start) / start * 100, 2) if start else 0.0,
                    "provider": account.get("provider") or "manual",
                    "synced_at": account.get("synced_at"),
                    "guard": guard.to_dict() if guard else None,
                    "curve": [r["balance"] for r in self.equity_curve(account["id"], days=30)],
                }
            )
        return {
            "konten": rows,
            "gesamt": round(total, 2),
            "gesamt_pnl": round(total - total_start, 2),
            "gesamt_pnl_pct": round((total - total_start) / total_start * 100, 2)
            if total_start else 0.0,
        }
