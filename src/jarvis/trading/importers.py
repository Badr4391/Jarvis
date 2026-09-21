"""CSV-Import von Broker-Exporten (MT4/MT5, cTrader, generisch)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

# Moegliche Spaltennamen je Zielfeld - case-insensitive, Leerzeichen egal.
ALIASES: dict[str, tuple[str, ...]] = {
    "external_id": ("ticket", "deal", "position", "order", "id", "orderid", "positionid"),
    "symbol": ("symbol", "instrument", "pair", "market"),
    "direction": ("type", "side", "direction", "action", "buy/sell"),
    "size": ("volume", "lots", "size", "quantity", "qty"),
    "entry": ("price", "openprice", "entryprice", "entry", "open"),
    "exit": ("closeprice", "exitprice", "exit", "close", "price2"),
    "stop_loss": ("s/l", "sl", "stoploss", "stop"),
    "take_profit": ("t/p", "tp", "takeprofit", "target"),
    "pnl": ("profit", "pnl", "netprofit", "p/l", "gross p/l", "netpl"),
    "fees": ("commission", "swap", "fees", "cost"),
    "opened_at": ("opentime", "time", "openingtime", "entrytime", "date", "opened"),
    "closed_at": ("closetime", "time2", "closingtime", "exittime", "closed"),
    "notes": ("comment", "note", "notes"),
}

DATE_FORMATS = (
    "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d.%m.%Y",
)


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "").replace("_", "").replace(".", "")


def _to_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    text = str(value).strip().replace(" ", "").replace(" ", "")
    if text.count(",") and text.count("."):
        text = text.replace(",", "")                  # 1,234.56
    elif text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")                 # 1234,56
    try:
        return float(text)
    except ValueError:
        return None


def _to_dt(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).isoformat(timespec="seconds")
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat(timespec="seconds")
    except ValueError:
        return None


def map_row(row: dict[str, Any]) -> dict[str, Any]:
    """Broker-Zeile auf Jarvis-Felder abbilden."""
    lookup = {_norm(k): v for k, v in row.items() if k}
    out: dict[str, Any] = {}
    for field, names in ALIASES.items():
        for candidate in names:
            key = _norm(candidate)
            if key in lookup and str(lookup[key]).strip() != "":
                out[field] = lookup[key]
                break

    direction = str(out.get("direction", "")).lower()
    out["direction"] = "short" if direction.startswith(("s", "sell", "v")) else "long"

    for field in ("size", "entry", "exit", "stop_loss", "take_profit", "pnl", "fees"):
        out[field] = _to_float(out.get(field))
    for field in ("opened_at", "closed_at"):
        out[field] = _to_dt(out.get(field))

    out["symbol"] = str(out.get("symbol", "")).strip().upper()
    out["pnl"] = out.get("pnl") or 0.0
    out["fees"] = out.get("fees") or 0.0
    out["external_id"] = str(out["external_id"]).strip() if out.get("external_id") else None
    out["notes"] = str(out.get("notes") or "")
    return out


def parse_csv(text: str) -> list[dict[str, Any]]:
    """CSV-Text lesen, Trennzeichen automatisch erkennen."""
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = []
    for raw in reader:
        mapped = map_row(raw)
        if mapped.get("symbol"):
            rows.append(mapped)
    return rows


def import_csv(journal, path: Path | str, *, account: str | int | None = None,
               skip_duplicates: bool = True) -> dict[str, Any]:
    """CSV in das Journal schreiben. Gibt eine Import-Zusammenfassung zurueck."""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    rows = parse_csv(text)
    imported, skipped = 0, 0
    for row in rows:
        if skip_duplicates and row.get("external_id"):
            acc = journal.get_account(account)
            existing = journal.db.one(
                "SELECT id FROM trades WHERE external_id = ? AND (account_id IS ? OR account_id = ?)",
                (row["external_id"], acc["id"] if acc else None, acc["id"] if acc else -1),
            )
            if existing:
                skipped += 1
                continue
        journal.log_trade(
            symbol=row["symbol"],
            direction=row["direction"],
            entry=row.get("entry"),
            exit=row.get("exit"),
            stop_loss=row.get("stop_loss"),
            take_profit=row.get("take_profit"),
            size=row.get("size"),
            pnl=float(row.get("pnl") or 0.0),
            fees=abs(float(row.get("fees") or 0.0)),
            opened_at=row.get("opened_at"),
            closed_at=row.get("closed_at"),
            account=account,
            notes=row.get("notes", ""),
            external_id=row.get("external_id"),
            update_balance=False,
        )
        imported += 1
    return {"file": str(path), "rows": len(rows), "imported": imported, "skipped": skipped}


def import_fundednext(journal, trades: Iterable[dict[str, Any]], *,
                      account: str | int | None = None) -> dict[str, Any]:
    """Trades aus der FundedNext-API (bereits als dicts) uebernehmen."""
    imported = 0
    for raw in trades:
        row = map_row(raw)
        if not row.get("symbol"):
            continue
        journal.log_trade(
            symbol=row["symbol"], direction=row["direction"], entry=row.get("entry"),
            exit=row.get("exit"), size=row.get("size"), pnl=float(row.get("pnl") or 0.0),
            fees=abs(float(row.get("fees") or 0.0)), opened_at=row.get("opened_at"),
            closed_at=row.get("closed_at"), account=account,
            external_id=row.get("external_id"), update_balance=False,
        )
        imported += 1
    return {"source": "fundednext", "imported": imported}
