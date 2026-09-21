"""Technische Indikatoren."""

import pytest

from jarvis.market.analysis import analyze_candles, atr, ema, rsi, sma, suggest_stop, swing_levels


def candles(closes, *, spread=1.0):
    return [
        {"date": f"2026-01-{i + 1:02d}", "open": c, "high": c + spread,
         "low": c - spread, "close": c}
        for i, c in enumerate(closes)
    ]


def test_sma_basic():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_too_short():
    assert sma([1, 2], 5) == [None, None]


def test_ema_starts_with_sma():
    values = ema([1, 2, 3, 4, 5, 6], 3)
    assert values[2] == pytest.approx(2.0)
    assert values[-1] > values[2]


def test_rsi_all_up_is_hundred():
    assert rsi(list(range(1, 20)), 14)[-1] == 100.0


def test_rsi_all_down_is_zero():
    assert rsi(list(range(20, 1, -1)), 14)[-1] == 0.0


def test_rsi_needs_enough_data():
    assert rsi([1, 2, 3], 14) == [None, None, None]


def test_atr_constant_range():
    rows = candles([100] * 20, spread=2.0)
    assert atr(rows, 14) == pytest.approx(4.0)


def test_swing_levels_finds_peak():
    rows = candles([1, 2, 3, 10, 3, 2, 1])
    levels = swing_levels(rows, lookback=2)
    assert 11.0 in levels["resistance"]


def test_uptrend_is_recognized():
    read = analyze_candles("EURUSD", candles([1.0 + i * 0.01 for i in range(220)]))
    assert read.bias == "long"
    assert read.trend == "Aufwaertstrend"
    assert read.strength >= 3


def test_downtrend_is_recognized():
    read = analyze_candles("EURUSD", candles([3.0 - i * 0.01 for i in range(220)]))
    assert read.bias == "short"


def test_needs_minimum_history():
    with pytest.raises(ValueError):
        analyze_candles("EURUSD", candles([1.0] * 5))


def test_suggest_stop_follows_bias():
    read = analyze_candles("EURUSD", candles([1.0 + i * 0.01 for i in range(220)]))
    levels = suggest_stop(read)
    assert levels["direction"] == "long"
    assert levels["stop_loss"] < read.price < levels["take_profit"]
