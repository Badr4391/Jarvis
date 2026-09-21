"""Trading-Journal, Konten und der Prop-Firm-Wachhund."""

from datetime import date, timedelta

import pytest

from jarvis.trading.journal import TradingJournal


@pytest.fixture()
def journal(db):
    j = TradingJournal(db)
    j.add_account("FN-100k", start_balance=100_000, broker="FundedNext",
                  max_daily_loss_pct=5, max_total_loss_pct=10, profit_target_pct=8)
    return j


def test_logging_a_trade_updates_balance(journal):
    journal.log_trade(symbol="eurusd", direction="buy", entry=1.085, exit=1.091,
                      stop_loss=1.082, pnl=600, fees=7, closed_at="2026-09-21T11:00:00")
    account = journal.get_account("FN-100k")
    assert account["balance"] == pytest.approx(100_593.0)


def test_r_multiple_is_derived(journal):
    trade = journal.log_trade(symbol="EURUSD", direction="long", entry=1.085, exit=1.091,
                              stop_loss=1.082, pnl=600, closed_at="2026-09-21T11:00:00")
    assert trade["r_multiple"] == 2.0


def test_direction_is_normalized(journal):
    assert journal.log_trade(symbol="X", direction="sell")["direction"] == "short"
    assert journal.log_trade(symbol="X", direction="kaufen")["direction"] == "long"


def test_open_trade_does_not_move_balance(journal):
    journal.log_trade(symbol="XAUUSD", direction="short", entry=2350, pnl=0)
    assert journal.get_account("FN-100k")["balance"] == 100_000
    assert len(journal.list_trades(open_only=True)) == 1


def test_close_trade_books_result(journal):
    trade = journal.log_trade(symbol="XAUUSD", direction="long", entry=2340, stop_loss=2330)
    closed = journal.close_trade(trade["id"], exit=2360, pnl=2000, fees=10)
    assert closed["r_multiple"] == 2.0
    assert journal.get_account("FN-100k")["balance"] == pytest.approx(101_990.0)


def test_realized_today_only_counts_today(journal):
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    journal.log_trade(symbol="A", direction="long", pnl=300, closed_at=f"{today}T10:00:00")
    journal.log_trade(symbol="B", direction="long", pnl=-100, closed_at=f"{today}T12:00:00")
    journal.log_trade(symbol="C", direction="long", pnl=999, closed_at=f"{yesterday}T12:00:00")
    assert journal.realized_today() == pytest.approx(200.0)


def test_guard_warns_before_the_limit(journal):
    today = date.today().isoformat()
    journal.log_trade(symbol="A", direction="long", pnl=-4900, closed_at=f"{today}T10:00:00")
    guard = journal.guard()
    assert guard.realized_today == pytest.approx(-4900.0)
    assert guard.daily_room == pytest.approx(100.0)       # 5% von 100k, davon 4900 verbraucht
    assert guard.status() == "VORSICHT"


def test_guard_stops_at_the_daily_limit(journal):
    today = date.today().isoformat()
    journal.log_trade(symbol="A", direction="long", pnl=-5000, closed_at=f"{today}T10:00:00")
    guard = journal.guard()
    assert guard.daily_room == 0.0
    assert guard.status() == "STOP"


def test_daily_status_shape(journal):
    status = journal.daily_status()
    assert status["account"] == "FN-100k"
    assert set(status) >= {"balance", "open_trades", "realized_today", "guard", "week"}


def test_stats_scoped_to_account(journal):
    journal.add_account("Zweitkonto", start_balance=10_000)
    today = date.today().isoformat()
    journal.log_trade(symbol="A", direction="long", pnl=100, account="FN-100k",
                      closed_at=f"{today}T10:00:00")
    journal.log_trade(symbol="B", direction="long", pnl=-50, account="Zweitkonto",
                      closed_at=f"{today}T10:00:00")
    assert journal.stats(account="FN-100k")["net_pnl"] == 100.0
    assert journal.stats(account="Zweitkonto")["net_pnl"] == -50.0
