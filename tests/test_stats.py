"""Journal-Kennzahlen."""


from jarvis.trading.stats import (
    by_symbol,
    by_weekday,
    compute_stats,
    find_leaks,
    max_drawdown,
    streaks,
)


def trade(pnl, *, symbol="EURUSD", setup="A", day="2026-09-01", fees=0.0, r=None, rating=None):
    return {
        "symbol": symbol, "setup": setup, "pnl": pnl, "fees": fees,
        "opened_at": f"{day}T09:00:00", "closed_at": f"{day}T11:00:00",
        "r_multiple": r, "rating": rating,
    }


def test_empty_set_is_safe():
    stats = compute_stats([])
    assert stats["trades"] == 0 and stats["winrate"] == 0.0


def test_open_trades_are_ignored():
    rows = [trade(100), {"symbol": "X", "pnl": 999, "closed_at": None, "opened_at": "2026-09-01"}]
    assert compute_stats(rows)["trades"] == 1


def test_core_metrics():
    rows = [trade(200), trade(-100), trade(300), trade(-100)]
    stats = compute_stats(rows)
    assert stats["trades"] == 4
    assert stats["winrate"] == 50.0
    assert stats["net_pnl"] == 300.0
    assert stats["profit_factor"] == 2.5          # 500 Gewinn / 200 Verlust
    assert stats["expectancy"] == 75.0
    assert stats["payoff_ratio"] == 2.5


def test_fees_reduce_result():
    assert compute_stats([trade(100, fees=10)])["net_pnl"] == 90.0


def test_equity_and_drawdown():
    rows = [trade(100), trade(-300), trade(50)]
    stats = compute_stats(rows, start_balance=1000)
    assert stats["equity"] == [1000, 1100, 800, 850]
    assert stats["max_drawdown"]["absolute"] == 300.0


def test_max_drawdown_percent():
    assert max_drawdown([100, 120, 60, 90])["percent"] == 50.0


def test_streaks():
    result = streaks([1, 1, 1, -1, -1, 1])
    assert result["best_win_streak"] == 3
    assert result["worst_loss_streak"] == 2
    assert result["current"] == 1


def test_grouping_sorted_by_result():
    rows = [trade(500, symbol="EURUSD"), trade(-200, symbol="XAUUSD"), trade(-100, symbol="XAUUSD")]
    grouped = by_symbol(rows)
    assert grouped[0]["key"] == "EURUSD"
    assert grouped[-1]["net_pnl"] == -300.0


def test_weekday_grouping_is_german():
    assert by_weekday([trade(100, day="2026-09-01")])[0]["key"] == "Dienstag"


def test_leaks_flag_losing_setup():
    rows = [trade(-100, setup="Fade") for _ in range(5)] + [trade(400, setup="Breakout")]
    hints = " ".join(find_leaks(rows))
    assert "Fade" in hints


def test_leaks_need_enough_data():
    assert find_leaks([trade(-100)]) == []
