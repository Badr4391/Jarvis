"""Technische Analyse ohne numpy: Indikatoren, Struktur, Bias."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any


def sma(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    window = sum(values[:period])
    out[period - 1] = window / period
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


def ema(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2 / (period + 1)
    current = sum(values[:period]) / period
    out[period - 1] = current
    for i in range(period, len(values)):
        current = values[i] * k + current * (1 - k)
        out[i] = current
    return out


def rsi(values: Sequence[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    out[period] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def atr(candles: Sequence[dict[str, Any]], period: int = 14) -> float | None:
    """Average True Range - Grundlage fuer Stop-Abstaende."""
    if len(candles) < period + 1:
        return None
    trs = []
    for prev, cur in zip(candles[-period - 1:-1], candles[-period:], strict=True):
        high, low = float(cur["high"]), float(cur["low"])
        close_prev = float(prev["close"])
        trs.append(max(high - low, abs(high - close_prev), abs(low - close_prev)))
    return sum(trs) / len(trs) if trs else None


def swing_levels(candles: Sequence[dict[str, Any]], *, lookback: int = 3,
                 limit: int = 4) -> dict[str, list[float]]:
    """Fraktale Hochs/Tiefs als Support- und Resistance-Kandidaten."""
    highs, lows = [], []
    for i in range(lookback, len(candles) - lookback):
        window = candles[i - lookback: i + lookback + 1]
        high, low = float(candles[i]["high"]), float(candles[i]["low"])
        if high == max(float(c["high"]) for c in window):
            highs.append(high)
        if low == min(float(c["low"]) for c in window):
            lows.append(low)
    return {"resistance": sorted(set(highs))[-limit:], "support": sorted(set(lows))[:limit]}


@dataclass
class SymbolRead:
    symbol: str
    price: float
    change_pct: float | None
    trend: str
    bias: str
    strength: int
    sma20: float | None
    sma50: float | None
    sma200: float | None
    rsi14: float | None
    atr14: float | None
    atr_pct: float | None
    support: list[float]
    resistance: list[float]
    range_position: float | None
    comments: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        arrow = "+" if (self.change_pct or 0) >= 0 else ""
        change = f"{arrow}{self.change_pct:.2f}%" if self.change_pct is not None else "n/a"
        return (
            f"{self.symbol} {self.price:g} ({change}) - {self.trend}, Bias {self.bias} "
            f"[{self.strength}/5]" + (f" | {self.comments[0]}" if self.comments else "")
        )


def analyze_candles(symbol: str, candles: Sequence[dict[str, Any]]) -> SymbolRead:
    """Aus Tageskerzen eine strukturierte Marktlesart bauen."""
    if len(candles) < 20:
        raise ValueError(f"Zu wenig Kerzen fuer {symbol} ({len(candles)})")

    closes = [float(c["close"]) for c in candles]
    price = closes[-1]
    prev = closes[-2] if len(closes) > 1 else price
    change_pct = ((price - prev) / prev * 100.0) if prev else None

    s20 = sma(closes, 20)[-1]
    s50 = sma(closes, 50)[-1]
    s200 = sma(closes, 200)[-1]
    r14 = rsi(closes, 14)[-1]
    a14 = atr(candles, 14)
    levels = swing_levels(candles)

    window = closes[-60:]
    low, high = min(window), max(window)
    range_position = ((price - low) / (high - low)) if high > low else None

    score = 0
    comments: list[str] = []
    if s20 and price > s20:
        score += 1
    elif s20:
        score -= 1
    if s50 and price > s50:
        score += 1
    elif s50:
        score -= 1
    if s200 and price > s200:
        score += 1
    elif s200:
        score -= 1
    if s20 and s50:
        score += 1 if s20 > s50 else -1
        comments.append("SMA20 ueber SMA50" if s20 > s50 else "SMA20 unter SMA50")
    if range_position is not None:
        if range_position > 0.8:
            score += 1
            comments.append("nahe 60-Tage-Hoch")
        elif range_position < 0.2:
            score -= 1
            comments.append("nahe 60-Tage-Tief")

    if score >= 2:
        trend, bias = "Aufwaertstrend", "long"
    elif score <= -2:
        trend, bias = "Abwaertstrend", "short"
    else:
        trend, bias = "Seitwaerts", "neutral"

    if r14 is not None:
        if r14 >= 70:
            comments.append(f"RSI {r14:.0f} - ueberkauft, Ruecksetzer moeglich")
        elif r14 <= 30:
            comments.append(f"RSI {r14:.0f} - ueberverkauft, Erholung moeglich")

    atr_pct = (a14 / price * 100.0) if a14 and price else None
    if atr_pct is not None and atr_pct > 2.5:
        comments.append(f"hohe Volatilitaet (ATR {atr_pct:.1f}%) - Position kleiner halten")

    return SymbolRead(
        symbol=symbol.upper(),
        price=round(price, 5),
        change_pct=round(change_pct, 2) if change_pct is not None else None,
        trend=trend,
        bias=bias,
        strength=min(5, abs(score)),
        sma20=round(s20, 5) if s20 else None,
        sma50=round(s50, 5) if s50 else None,
        sma200=round(s200, 5) if s200 else None,
        rsi14=round(r14, 1) if r14 else None,
        atr14=round(a14, 5) if a14 else None,
        atr_pct=round(atr_pct, 2) if atr_pct else None,
        support=[round(v, 5) for v in levels["support"]],
        resistance=[round(v, 5) for v in levels["resistance"]],
        range_position=round(range_position, 2) if range_position is not None else None,
        comments=comments,
    )


def suggest_stop(read: SymbolRead, *, multiple: float = 1.5) -> dict[str, Any]:
    """ATR-basierter Stop-Vorschlag passend zum Bias."""
    if not read.atr14:
        return {"error": "kein ATR verfuegbar"}
    distance = read.atr14 * multiple
    if read.bias == "short":
        return {
            "direction": "short", "entry": read.price,
            "stop_loss": round(read.price + distance, 5),
            "take_profit": round(read.price - distance * 2, 5),
            "atr_multiple": multiple, "rr": 2.0,
        }
    return {
        "direction": "long", "entry": read.price,
        "stop_loss": round(read.price - distance, 5),
        "take_profit": round(read.price + distance * 2, 5),
        "atr_multiple": multiple, "rr": 2.0,
    }
