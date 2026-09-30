"""Konto-Anbindungen: Abgleich, FundedNext-Zuordnung, Portfolio."""

from datetime import date, timedelta

import pytest

from jarvis.connectors.base import AccountSnapshot, ConnectorError
from jarvis.connectors.fundednext import FundedNextConnector
from jarvis.connectors.sync import AccountSync
from jarvis.trading.journal import TradingJournal


@pytest.fixture()
def sync(db):
    return AccountSync(db=db, journal=TradingJournal(db))


def snapshot(**kwargs) -> AccountSnapshot:
    base = dict(name="FN-512345", balance=104_200.0, equity=103_900.0, start_balance=100_000.0,
                provider="fundednext", external_id="8891", login="512345",
                phase="Stellar 2-Step 100K", broker="FundedNext",
                max_daily_loss_pct=5.0, max_total_loss_pct=10.0, profit_target_pct=8.0)
    base.update(kwargs)
    return AccountSnapshot(**base)


def test_first_snapshot_creates_account(sync):
    result = sync.apply(snapshot())
    assert result["neu"] is True
    account = sync.journal.get_account("FN-512345")
    assert account["balance"] == 104_200.0
    assert account["start_balance"] == 100_000.0
    assert account["provider"] == "fundednext"


def test_second_snapshot_updates_instead_of_duplicating(sync):
    sync.apply(snapshot())
    sync.apply(snapshot(balance=105_000.0))
    assert len(sync.journal.list_accounts()) == 1
    assert sync.journal.get_account("FN-512345")["balance"] == 105_000.0


def test_renamed_account_is_matched_by_external_id(sync):
    sync.apply(snapshot())
    sync.apply(snapshot(name="Ganz anderer Name", balance=99_000.0))
    accounts = sync.journal.list_accounts()
    assert len(accounts) == 1
    assert accounts[0]["balance"] == 99_000.0


def test_breached_account_is_deactivated(sync):
    sync.apply(snapshot(status="breached"))
    assert sync.journal.list_accounts(active_only=True) == []


def test_limits_from_provider_win(sync):
    sync.apply(snapshot(max_daily_loss_pct=4.0, profit_target_pct=10.0))
    account = sync.journal.get_account("FN-512345")
    assert account["max_daily_loss_pct"] == 4.0
    assert account["profit_target_pct"] == 10.0


def test_balance_history_is_recorded(sync):
    sync.apply(snapshot())
    curve = sync.equity_curve(1)
    assert len(curve) == 1 and curve[0]["balance"] == 104_200.0


def test_same_day_twice_keeps_one_point(sync):
    sync.apply(snapshot())
    sync.apply(snapshot(balance=106_000.0))
    curve = sync.equity_curve(1)
    assert len(curve) == 1 and curve[0]["balance"] == 106_000.0


def test_equity_curve_is_chronological(sync):
    sync.apply(snapshot())
    for offset, value in ((3, 101_000), (2, 102_000), (1, 103_000)):
        sync.record_balance(1, value, day=(date.today() - timedelta(days=offset)).isoformat())
    assert [row["balance"] for row in sync.equity_curve(1)] == \
        [101_000, 102_000, 103_000, 104_200.0]


def test_portfolio_totals(sync):
    sync.apply(snapshot())
    sync.apply(snapshot(name="Zweit", external_id="42", balance=27_000.0, start_balance=25_000.0))
    portfolio = sync.portfolio()
    assert portfolio["gesamt"] == 131_200.0
    assert portfolio["gesamt_pnl"] == 6_200.0
    assert len(portfolio["konten"]) == 2
    assert portfolio["konten"][0]["guard"]["status"] == "OK"


def test_run_collects_errors_instead_of_raising(sync):
    class Broken:
        name = "kaputt"

        def enabled(self):
            return True

        def fetch(self):
            raise ConnectorError("Token abgelaufen")

    result = sync.run([Broken()])
    assert result["konten"] == []
    assert "Token abgelaufen" in result["fehler"][0]


def test_run_without_connectors_explains_what_to_do(sync):
    assert "FUNDEDNEXT_TOKEN" in sync.run([])["fehler"][0]


# ------------------------------------------------------ FundedNext-Zuordnung


def test_connector_disabled_without_token():
    assert FundedNextConnector(token="").enabled() is False
    assert FundedNextConnector(token="abc").enabled() is True


def test_missing_token_gives_a_useful_message():
    with pytest.raises(ConnectorError, match="FUNDEDNEXT_TOKEN"):
        FundedNextConnector(token="")._get("accounts")


def test_rows_unwraps_nested_payloads():
    rows = FundedNextConnector._rows
    assert rows([{"a": 1}]) == [{"a": 1}]
    assert rows({"data": [{"a": 1}]}) == [{"a": 1}]
    assert rows({"data": {"data": [{"a": 1}]}}) == [{"a": 1}]
    assert rows({"nichts": 1}) == []


def test_row_maps_to_snapshot():
    # overview_path leer: nur die Zuordnung pruefen, kein Netzzugriff
    connector = FundedNextConnector(token="x", overview_path="")
    result = connector._to_snapshot({
        "id": 8891, "login": "512345", "plan": "Stellar 2-Step 100K",
        "balance": "104200.00", "equity": "103900.00", "breached": 0, "status": "active",
    })
    assert result.name == "FN-512345"
    assert result.balance == 104_200.0
    assert result.external_id == "8891"
    assert result.phase == "Stellar 2-Step 100K"
    assert result.status == "active"


def test_row_without_balance_is_skipped():
    connector = FundedNextConnector(token="x", overview_path="")
    assert connector._to_snapshot({"id": 1, "login": "9"}) is None


def test_breached_flag_is_honoured():
    connector = FundedNextConnector(token="x", overview_path="")
    result = connector._to_snapshot({"id": 1, "login": "9", "balance": 90_000, "breached": 1})
    assert result.status == "breached"


def test_plan_name_used_when_login_missing():
    connector = FundedNextConnector(token="x", overview_path="")
    result = connector._to_snapshot({"id": 77, "plan": "Stellar Lite 25K", "balance": 25_000})
    assert result.name == "Stellar Lite 25K"
    assert result.external_id == "77"
