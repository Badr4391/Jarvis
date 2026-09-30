"""Gemeinsame Form fuer alle Konto-Anbindungen."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass
class AccountSnapshot:
    """Ein Kontostand, wie ihn ein Anbieter gerade meldet."""

    name: str
    balance: float
    equity: float | None = None
    currency: str = "USD"
    start_balance: float | None = None
    provider: str = "manual"
    external_id: str | None = None
    login: str | None = None
    phase: str = ""
    broker: str = ""
    status: str = "active"
    # Verbleibende Puffer laut Anbieter - genauer als jede eigene Rechnung.
    daily_loss_left: float | None = None
    total_loss_left: float | None = None
    profit_target_left: float | None = None
    max_daily_loss_pct: float | None = None
    max_total_loss_pct: float | None = None
    profit_target_pct: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("raw", None)
        return data


class AccountConnector(Protocol):
    name: str

    def enabled(self) -> bool: ...

    def fetch(self) -> list[AccountSnapshot]: ...


class ConnectorError(RuntimeError):
    """Anbindung nicht erreichbar oder nicht eingerichtet."""
