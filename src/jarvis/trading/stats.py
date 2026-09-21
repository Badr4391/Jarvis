"""Auswertung des Trading-Journals: Kennzahlen, Equity-Kurve, Muster."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime
from statistics import mean, pstdev
from typing import Any

WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def _net(trade: dict[str, Any]) -> float:
    return float(trade.get("pnl") or 0.0) - float(trade.get("fees") or 0.0)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    for candidate in (text, text[:19], text[:10]):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def max_drawdown(equity: Sequence[float]) -> dict[str, float]:
    """Groesster Ruecksetzer der Equity-Kurve, absolut und in Prozent."""
    peak = equity[0] if equity else 0.0
    worst_abs = 0.0
    worst_pct = 0.0
    for value in equity:
        peak = max(peak, value)
        drop = peak - value
        if drop > worst_abs:
            worst_abs = drop
            worst_pct = (drop / peak * 100.0) if peak else 0.0
    return {"absolute": round(worst_abs, 2), "percent": round(worst_pct, 2)}


def streaks(results: Iterable[float]) -> dict[str, int]:
    """Laengste Gewinn-/Verlustserie und die aktuelle Serie."""
    best = worst = current = 0
    for value in results:
        if value > 0:
            current = current + 1 if current > 0 else 1
            best = max(best, current)
        elif value < 0:
            current = current - 1 if current < 0 else -1
            worst = min(worst, current)
        else:
            current = 0
    return {"best_win_streak": best, "worst_loss_streak": abs(worst), "current": current}


def compute_stats(trades: Sequence[dict[str, Any]], *, start_balance: float = 0.0) -> dict[str, Any]:
    """Alle Kernkennzahlen eines Trade-Sets."""
    closed = [t for t in trades if t.get("closed_at")]
    if not closed:
        return {
            "trades": 0, "wins": 0, "losses": 0, "winrate": 0.0, "net_pnl": 0.0,
            "profit_factor": 0.0, "expectancy": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "avg_r": 0.0, "best": 0.0, "worst": 0.0, "max_drawdown": {"absolute": 0.0, "percent": 0.0},
            "streaks": {"best_win_streak": 0, "worst_loss_streak": 0, "current": 0},
            "equity": [start_balance] if start_balance else [],
        }

    closed = sorted(closed, key=lambda t: str(t.get("closed_at") or t.get("opened_at") or ""))
    nets = [_net(t) for t in closed]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    r_values = [float(t["r_multiple"]) for t in closed if t.get("r_multiple") is not None]

    equity, running = [start_balance], start_balance
    for net in nets:
        running += net
        equity.append(running)

    winrate = len(wins) / len(nets) * 100.0
    avg_win = mean(wins) if wins else 0.0
    avg_loss = mean(losses) if losses else 0.0

    return {
        "trades": len(nets),
        "wins": len(wins),
        "losses": len(losses),
        "winrate": round(winrate, 1),
        "net_pnl": round(sum(nets), 2),
        "gross_profit": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else (999.0 if gross_win else 0.0),
        "expectancy": round(mean(nets), 2),
        "expectancy_r": round(mean(r_values), 2) if r_values else 0.0,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "payoff_ratio": round(abs(avg_win / avg_loss), 2) if avg_loss else 0.0,
        "avg_r": round(mean(r_values), 2) if r_values else 0.0,
        "stdev": round(pstdev(nets), 2) if len(nets) > 1 else 0.0,
        "best": round(max(nets), 2),
        "worst": round(min(nets), 2),
        "max_drawdown": max_drawdown(equity),
        "streaks": streaks(nets),
        "equity": [round(v, 2) for v in equity],
    }


def _group(trades: Sequence[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        if not trade.get("closed_at"):
            continue
        key = key_fn(trade)
        if key is None:
            continue
        buckets[str(key)].append(trade)

    rows = []
    for key, group in buckets.items():
        nets = [_net(t) for t in group]
        wins = [n for n in nets if n > 0]
        rows.append(
            {
                "key": key,
                "trades": len(group),
                "net_pnl": round(sum(nets), 2),
                "winrate": round(len(wins) / len(nets) * 100.0, 1),
                "avg": round(mean(nets), 2),
            }
        )
    return sorted(rows, key=lambda r: r["net_pnl"], reverse=True)


def by_symbol(trades: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return _group(trades, lambda t: (t.get("symbol") or "?").upper())


def by_setup(trades: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return _group(trades, lambda t: t.get("setup") or "ohne Setup")


def by_weekday(trades: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(trade):
        dt = _parse_dt(trade.get("opened_at"))
        return WEEKDAYS_DE[dt.weekday()] if dt else None

    return _group(trades, key)


def by_hour(trades: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(trade):
        dt = _parse_dt(trade.get("opened_at"))
        return f"{dt.hour:02d}:00" if dt else None

    return _group(trades, key)


def find_leaks(trades: Sequence[dict[str, Any]], *, min_trades: int = 4) -> list[str]:
    """Konkrete, umsetzbare Hinweise - keine Motivationsspruechen."""
    hints: list[str] = []
    stats = compute_stats(trades)
    if stats["trades"] < min_trades:
        return hints

    if stats["payoff_ratio"] and stats["payoff_ratio"] < 1.0 and stats["winrate"] < 55:
        hints.append(
            f"Payoff {stats['payoff_ratio']} bei {stats['winrate']}% Trefferquote - "
            "Gewinner laufen lassen oder Stop enger setzen."
        )
    if stats["profit_factor"] < 1.0:
        hints.append(f"Profit-Faktor {stats['profit_factor']} - das System verliert aktuell Geld.")
    if stats["streaks"]["worst_loss_streak"] >= 4:
        hints.append(
            f"Laengste Verlustserie: {stats['streaks']['worst_loss_streak']} Trades - "
            "nach 3 Verlusten in Folge Handelstag beenden."
        )

    for bucket, label in ((by_symbol(trades), "Symbol"), (by_setup(trades), "Setup"),
                          (by_weekday(trades), "Wochentag")):
        losers = [b for b in bucket if b["trades"] >= min_trades and b["net_pnl"] < 0]
        for row in losers[-2:]:
            hints.append(
                f"{label} {row['key']}: {row['trades']} Trades, {row['net_pnl']} netto "
                f"({row['winrate']}% Treffer) - streichen oder Regeln nachschaerfen."
            )

    rated = [t for t in trades if t.get("rating") and t.get("closed_at")]
    if len(rated) >= min_trades:
        good = [_net(t) for t in rated if int(t["rating"]) >= 4]
        bad = [_net(t) for t in rated if int(t["rating"]) <= 2]
        if good and bad and mean(good) > mean(bad):
            hints.append(
                f"Saubere Ausfuehrung bringt im Schnitt {round(mean(good), 2)}, "
                f"schlampige {round(mean(bad), 2)} - Checkliste vor jedem Entry."
            )
    return hints
