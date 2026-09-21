"""Risiko-Rechner: Positionsgroesse, R-Multiple, Prop-Firm Limits."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Kontraktgroessen / Pip-Definitionen je Instrumentenklasse.
JPY_QUOTE = ("JPY",)
METALS = {"XAUUSD": 100.0, "XAGUSD": 5000.0}       # Unzen pro Standard-Lot
INDEX_LIKE = ("US30", "NAS100", "SPX500", "GER40", "DAX", "^")
CRYPTO_LIKE = ("BTC", "ETH", "SOL", "XRP")


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace("/", "").replace("_", "")


def pip_size(symbol: str) -> float:
    """Kleinste sinnvolle Kursbewegung (1 Pip bzw. 1 Punkt)."""
    sym = normalize_symbol(symbol)
    if sym in METALS:
        return 0.01
    if any(sym.startswith(c) for c in CRYPTO_LIKE):
        return 1.0
    if any(tag in sym for tag in INDEX_LIKE):
        return 1.0
    if len(sym) == 6:                               # FX Paar
        return 0.01 if sym[3:] in JPY_QUOTE else 0.0001
    return 0.0001


def contract_size(symbol: str) -> float:
    """Einheiten pro 1.0 Lot."""
    sym = normalize_symbol(symbol)
    if sym in METALS:
        return METALS[sym]
    if any(sym.startswith(c) for c in CRYPTO_LIKE):
        return 1.0
    if any(tag in sym for tag in INDEX_LIKE):
        return 1.0
    if len(sym) == 6:
        return 100_000.0
    return 1.0


def quote_currency(symbol: str) -> str:
    """Notierungswaehrung - bestimmt, ob umgerechnet werden muss."""
    sym = normalize_symbol(symbol)
    if sym in METALS or any(tag in sym for tag in INDEX_LIKE):
        return "USD"
    if len(sym) in (6, 7) and sym[-3:].isalpha():
        return sym[-3:]
    return "USD"


def value_per_point(symbol: str, *, quote_to_account_rate: float = 1.0) -> float:
    """Kontowaehrungs-Wert einer 1-Pip-Bewegung bei 1.0 Lot."""
    return pip_size(symbol) * contract_size(symbol) * quote_to_account_rate


@dataclass
class PositionSize:
    symbol: str
    risk_amount: float
    stop_distance: float
    stop_pips: float
    value_per_point: float
    lots: float
    units: float
    risk_pct: float
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def position_size(
    *,
    symbol: str,
    balance: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    quote_to_account_rate: float | None = None,
    account_currency: str = "USD",
    max_lots: float | None = None,
    min_lots: float = 0.01,
) -> PositionSize:
    """Lot-Groesse fuer ein definiertes Risiko in Prozent des Kontos.

    Ist die Notierungswaehrung nicht die Kontowaehrung (z.B. USDJPY auf einem
    USD-Konto), muss ``quote_to_account_rate`` gesetzt werden - sonst rechnet
    Jarvis mit 1.0 weiter und schreibt eine Warnung in ``note``.
    """
    if balance <= 0:
        raise ValueError("balance muss groesser als 0 sein")
    if risk_pct <= 0:
        raise ValueError("risk_pct muss groesser als 0 sein")
    stop_distance = abs(entry - stop_loss)
    if stop_distance <= 0:
        raise ValueError("Stop-Loss darf nicht auf dem Entry liegen")

    notes: list[str] = []
    quote = quote_currency(symbol)
    if quote_to_account_rate is None:
        quote_to_account_rate = 1.0
        if quote != account_currency.upper():
            notes.append(
                f"Kurs {quote}->{account_currency.upper()} fehlt - Lotgroesse ist noch nicht "
                f"in {account_currency.upper()} umgerechnet"
            )

    risk_amount = balance * (risk_pct / 100.0)
    p_size = pip_size(symbol)
    stop_pips = stop_distance / p_size
    vpp = value_per_point(symbol, quote_to_account_rate=quote_to_account_rate)
    lots = risk_amount / (stop_pips * vpp) if stop_pips and vpp else 0.0

    if max_lots is not None and lots > max_lots:
        notes.append(f"auf max_lots={max_lots} gedeckelt")
        lots = max_lots

    lots = round(lots, 2)
    if lots < min_lots:
        notes.append(
            f"rechnerisch {round(risk_amount / (stop_pips * vpp), 4) if stop_pips and vpp else 0} Lot - "
            f"unter Mindestgroesse {min_lots}, Stop verkleinern oder Trade auslassen"
        )
        lots = 0.0
    return PositionSize(
        symbol=normalize_symbol(symbol),
        risk_amount=round(risk_amount, 2),
        stop_distance=round(stop_distance, 6),
        stop_pips=round(stop_pips, 1),
        value_per_point=round(vpp, 4),
        lots=lots,
        units=round(lots * contract_size(symbol), 2),
        risk_pct=risk_pct,
        note="; ".join(notes),
    )


def r_multiple(*, entry: float, exit_price: float, stop_loss: float, direction: str) -> float:
    """Ergebnis in R (Vielfaches des Anfangsrisikos)."""
    risk = abs(entry - stop_loss)
    if risk <= 0:
        return 0.0
    move = (exit_price - entry) if direction.lower().startswith("l") else (entry - exit_price)
    return round(move / risk, 2)


def reward_risk(*, entry: float, stop_loss: float, take_profit: float) -> float:
    risk = abs(entry - stop_loss)
    if risk <= 0:
        return 0.0
    return round(abs(take_profit - entry) / risk, 2)


@dataclass
class PropGuard:
    """Prop-Firm Wachhund: wie viel Risiko ist heute noch erlaubt."""

    account: str
    balance: float
    start_balance: float
    daily_start_balance: float
    max_daily_loss_pct: float
    max_total_loss_pct: float
    profit_target_pct: float
    realized_today: float = 0.0

    @property
    def daily_loss_limit(self) -> float:
        return self.daily_start_balance * (self.max_daily_loss_pct / 100.0)

    @property
    def total_loss_limit(self) -> float:
        return self.start_balance * (self.max_total_loss_pct / 100.0)

    @property
    def daily_room(self) -> float:
        used = max(0.0, -self.realized_today)
        return max(0.0, self.daily_loss_limit - used)

    @property
    def total_room(self) -> float:
        drawdown = max(0.0, self.start_balance - self.balance)
        return max(0.0, self.total_loss_limit - drawdown)

    @property
    def room(self) -> float:
        return min(self.daily_room, self.total_room)

    @property
    def target_remaining(self) -> float:
        target = self.start_balance * (1 + self.profit_target_pct / 100.0)
        return max(0.0, target - self.balance)

    def status(self) -> str:
        if self.room <= 0:
            return "STOP"
        if self.room < self.daily_loss_limit * 0.35:
            return "VORSICHT"
        return "OK"

    def max_risk_for_trade(self, *, risk_pct: float, trades_left: int = 1) -> float:
        """Erlaubtes Risiko fuer den naechsten Trade in Kontowaehrung."""
        wish = self.balance * (risk_pct / 100.0)
        budget = self.room / max(1, trades_left)
        return round(min(wish, budget), 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "balance": round(self.balance, 2),
            "status": self.status(),
            "daily_loss_limit": round(self.daily_loss_limit, 2),
            "daily_room": round(self.daily_room, 2),
            "total_loss_limit": round(self.total_loss_limit, 2),
            "total_room": round(self.total_room, 2),
            "room": round(self.room, 2),
            "realized_today": round(self.realized_today, 2),
            "target_remaining": round(self.target_remaining, 2),
        }
