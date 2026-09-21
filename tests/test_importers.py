"""CSV-Import aus Broker-Exporten."""


from jarvis.trading.importers import import_csv, map_row, parse_csv
from jarvis.trading.journal import TradingJournal

MT5_EXPORT = """Ticket;Open Time;Type;Volume;Symbol;Price;S / L;T / P;Close Time;Price2;Commission;Swap;Profit
12345;2026.09.15 09:12:03;buy;1.00;EURUSD;1.08500;1.08200;1.09100;2026.09.15 11:02:10;1.09100;-7,00;0,00;600,00
12346;2026.09.16 14:02:03;sell;0.50;XAUUSD;2350.10;2358.00;2335.00;2026.09.16 15:20:00;2358.00;-3,50;0,00;-395,00
"""

COMMA_EXPORT = """id,date,side,symbol,qty,entryprice,exitprice,pnl
A-1,2026-09-10 08:00:00,SELL,GBPUSD,0.25,1.27500,1.27100,95.50
"""


def test_parse_semicolon_export():
    rows = parse_csv(MT5_EXPORT)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "EURUSD"
    assert rows[0]["direction"] == "long"
    assert rows[0]["pnl"] == 600.0
    assert rows[0]["opened_at"] == "2026-09-15T09:12:03"


def test_parse_comma_export_with_aliases():
    row = parse_csv(COMMA_EXPORT)[0]
    assert row["direction"] == "short"
    assert row["entry"] == 1.275
    assert row["exit"] == 1.271
    assert row["external_id"] == "A-1"


def test_german_decimal_comma():
    assert map_row({"Profit": "1234,56", "Symbol": "X", "Type": "buy"})["pnl"] == 1234.56


def test_thousand_separator():
    assert map_row({"Profit": "1,234.56", "Symbol": "X", "Type": "buy"})["pnl"] == 1234.56


def test_import_is_idempotent(db, tmp_path):
    journal = TradingJournal(db)
    journal.add_account("MT5", start_balance=50_000)
    path = tmp_path / "export.csv"
    path.write_text(MT5_EXPORT, encoding="utf-8")

    first = import_csv(journal, path, account="MT5")
    second = import_csv(journal, path, account="MT5")
    assert first["imported"] == 2
    assert second["imported"] == 0 and second["skipped"] == 2
    assert len(journal.list_trades()) == 2


def test_import_computes_r_multiple(db, tmp_path):
    journal = TradingJournal(db)
    journal.add_account("MT5", start_balance=50_000)
    path = tmp_path / "export.csv"
    path.write_text(MT5_EXPORT, encoding="utf-8")
    import_csv(journal, path, account="MT5")
    eurusd = [t for t in journal.list_trades() if t["symbol"] == "EURUSD"][0]
    assert eurusd["r_multiple"] == 2.0
