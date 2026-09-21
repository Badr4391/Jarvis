"""Risiko-Mathematik - hier darf nichts daneben gehen."""

import pytest

from jarvis.trading.risk import (
    PropGuard,
    pip_size,
    position_size,
    quote_currency,
    r_multiple,
    reward_risk,
    value_per_point,
)


def test_pip_size_per_asset_class():
    assert pip_size("EURUSD") == 0.0001
    assert pip_size("USDJPY") == 0.01
    assert pip_size("XAUUSD") == 0.01
    assert pip_size("BTCUSD") == 1.0


def test_value_per_point_standard_lot():
    assert value_per_point("EURUSD") == pytest.approx(10.0)
    assert value_per_point("XAUUSD") == pytest.approx(1.0)


def test_position_size_matches_manual_math():
    # 0.5% von 100.000 = 500 USD Risiko, 30 Pips Stop, 10 USD je Pip -> 1.67 Lot
    sizing = position_size(symbol="EURUSD", balance=100_000, risk_pct=0.5,
                           entry=1.0850, stop_loss=1.0820)
    assert sizing.risk_amount == 500.0
    assert sizing.stop_pips == 30.0
    assert sizing.lots == pytest.approx(1.67, abs=0.01)


def test_position_size_respects_max_lots():
    sizing = position_size(symbol="EURUSD", balance=100_000, risk_pct=2.0,
                           entry=1.0850, stop_loss=1.0845, max_lots=1.0)
    assert sizing.lots == 1.0
    assert "max_lots" in sizing.note


def test_position_size_warns_when_conversion_missing():
    sizing = position_size(symbol="USDJPY", balance=10_000, risk_pct=1.0,
                           entry=150.0, stop_loss=149.5)
    assert "JPY" in sizing.note


def test_position_size_with_conversion_rate():
    sizing = position_size(symbol="USDJPY", balance=10_000, risk_pct=1.0,
                           entry=150.0, stop_loss=149.5, quote_to_account_rate=1 / 150)
    assert sizing.lots == pytest.approx(0.3, abs=0.01)
    assert sizing.note == ""


def test_position_size_flags_sub_minimum_size():
    sizing = position_size(symbol="EURUSD", balance=500, risk_pct=0.5,
                           entry=1.0850, stop_loss=1.0350)
    assert sizing.lots == 0.0
    assert "Mindestgroesse" in sizing.note


def test_position_size_rejects_zero_stop():
    with pytest.raises(ValueError):
        position_size(symbol="EURUSD", balance=1000, risk_pct=1, entry=1.08, stop_loss=1.08)


def test_quote_currency():
    assert quote_currency("EURUSD") == "USD"
    assert quote_currency("USDJPY") == "JPY"
    assert quote_currency("XAUUSD") == "USD"


def test_r_multiple_both_directions():
    assert r_multiple(entry=100, exit_price=110, stop_loss=95, direction="long") == 2.0
    assert r_multiple(entry=100, exit_price=90, stop_loss=105, direction="short") == 2.0
    assert r_multiple(entry=100, exit_price=95, stop_loss=95, direction="long") == -1.0


def test_reward_risk():
    assert reward_risk(entry=100, stop_loss=95, take_profit=115) == 3.0


def _guard(**kwargs) -> PropGuard:
    base = dict(account="FN", balance=100_000, start_balance=100_000,
                daily_start_balance=100_000, max_daily_loss_pct=5,
                max_total_loss_pct=10, profit_target_pct=8, realized_today=0.0)
    base.update(kwargs)
    return PropGuard(**base)


def test_prop_guard_fresh_account_is_ok():
    guard = _guard()
    assert guard.status() == "OK"
    assert guard.daily_room == 5000.0
    assert guard.total_room == 10_000.0


def test_prop_guard_warns_then_stops():
    warn = _guard(balance=96_500, realized_today=-3_500)
    assert warn.status() == "VORSICHT"
    stop = _guard(balance=95_000, realized_today=-5_000)
    assert stop.status() == "STOP"
    assert stop.room == 0.0


def test_prop_guard_total_drawdown_caps_daily_room():
    guard = _guard(balance=91_000, daily_start_balance=91_000, realized_today=0.0)
    assert guard.total_room == 1_000.0
    assert guard.room == 1_000.0          # Gesamtpuffer ist enger als das Tageslimit


def test_prop_guard_splits_budget_across_trades():
    guard = _guard(balance=100_000, realized_today=-4_000, daily_start_balance=100_000)
    # 1000 USD Restpuffer, auf 2 Trades verteilt -> 500 statt der gewuenschten 1000
    assert guard.max_risk_for_trade(risk_pct=1.0, trades_left=2) == 500.0
