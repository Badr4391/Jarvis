"""Trading-Journal: Konten, Trades, Tagesstatus, Prop-Firm Wachhund."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from jarvis.storage.db import Database, utcnow
from jarvis.trading import stats as stats_mod
from jarvis.trading.risk import PropGuard, r_multiple


@dataclass
class TradingJournal:
    db: Database

    # -------------------------------------------------------------- accounts
    def add_account(
        self,
        name: str,
        *,
        start_balance: float,
        balance: float | None = None,
        broker: str = "",
        kind: str = "prop",
        currency: str = "USD",
        max_daily_loss_pct: float = 5.0,
        max_total_loss_pct: float = 10.0,
        profit_target_pct: float = 8.0,
        phase: str = "",
    ) -> dict[str, Any]:
        self.db.execute(
            "INSERT INTO accounts(name, broker, kind, currency, start_balance, balance, "
            "max_daily_loss_pct, max_total_loss_pct, profit_target_pct, phase, active, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,1,?) "
            "ON CONFLICT(name) DO UPDATE SET broker=excluded.broker, kind=excluded.kind, "
            "currency=excluded.currency, start_balance=excluded.start_balance, "
            "balance=excluded.balance, max_daily_loss_pct=excluded.max_daily_loss_pct, "
            "max_total_loss_pct=excluded.max_total_loss_pct, "
            "profit_target_pct=excluded.profit_target_pct, phase=excluded.phase, active=1",
            (
                name.strip(), broker, kind, currency, start_balance,
                balance if balance is not None else start_balance,
                max_daily_loss_pct, max_total_loss_pct, profit_target_pct, phase, utcnow(),
            ),
        )
        return self.get_account(name) or {}

    def get_account(self, ref: str | int | None) -> dict[str, Any] | None:
        if ref is None:
            return self.db.one("SELECT * FROM accounts WHERE active = 1 ORDER BY id LIMIT 1")
        if isinstance(ref, int) or str(ref).isdigit():
            return self.db.one("SELECT * FROM accounts WHERE id = ?", (int(ref),))
        return self.db.one("SELECT * FROM accounts WHERE lower(name) = ?", (str(ref).strip().lower(),))

    def list_accounts(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM accounts"
        if active_only:
            sql += " WHERE active = 1"
        return self.db.query(sql + " ORDER BY id")

    def set_balance(self, ref: str | int, balance: float) -> dict[str, Any] | None:
        account = self.get_account(ref)
        if not account:
            return None
        self.db.update("accounts", account["id"], {"balance": balance})
        return self.get_account(account["id"])

    # ---------------------------------------------------------------- trades
    def log_trade(
        self,
        *,
        symbol: str,
        direction: str,
        entry: float | None = None,
        exit: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        size: float | None = None,
        pnl: float = 0.0,
        fees: float = 0.0,
        opened_at: str | None = None,
        closed_at: str | None = None,
        account: str | int | None = None,
        setup: str = "",
        session: str = "",
        tags: str = "",
        emotion: str = "",
        rating: int | None = None,
        notes: str = "",
        risk_amount: float | None = None,
        external_id: str | None = None,
        update_balance: bool = True,
    ) -> dict[str, Any]:
        acc = self.get_account(account)
        direction = "long" if direction.lower().startswith(("l", "b", "k")) else "short"

        r_value = None
        if entry is not None and exit is not None and stop_loss is not None:
            r_value = r_multiple(entry=entry, exit_price=exit, stop_loss=stop_loss, direction=direction)
        elif risk_amount:
            r_value = round((pnl - fees) / risk_amount, 2)

        trade_id = self.db.insert(
            "trades",
            {
                "account_id": acc["id"] if acc else None,
                "symbol": symbol.strip().upper(),
                "direction": direction,
                "opened_at": opened_at or utcnow(),
                "closed_at": closed_at,
                "entry": entry,
                "exit": exit,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "size": size,
                "pnl": pnl,
                "fees": fees,
                "risk_amount": risk_amount,
                "r_multiple": r_value,
                "setup": setup,
                "session": session,
                "tags": tags,
                "emotion": emotion,
                "rating": rating,
                "notes": notes,
                "external_id": external_id,
                "created_at": utcnow(),
            },
        )
        if acc and update_balance and closed_at:
            self.db.update("accounts", acc["id"], {"balance": acc["balance"] + pnl - fees})
        return self.get_trade(trade_id) or {}

    def get_trade(self, trade_id: int) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM trades WHERE id = ?", (trade_id,))

    def close_trade(
        self, trade_id: int, *, exit: float, pnl: float, fees: float = 0.0,
        closed_at: str | None = None, notes: str = "", rating: int | None = None,
    ) -> dict[str, Any] | None:
        trade = self.get_trade(trade_id)
        if not trade:
            return None
        values: dict[str, Any] = {
            "exit": exit, "pnl": pnl, "fees": fees,
            "closed_at": closed_at or utcnow(),
        }
        if notes:
            values["notes"] = (trade["notes"] + "\n" + notes).strip()
        if rating is not None:
            values["rating"] = rating
        if trade["entry"] is not None and trade["stop_loss"] is not None:
            values["r_multiple"] = r_multiple(
                entry=trade["entry"], exit_price=exit,
                stop_loss=trade["stop_loss"], direction=trade["direction"],
            )
        self.db.update("trades", trade_id, values)
        if trade["account_id"]:
            acc = self.get_account(trade["account_id"])
            if acc:
                self.db.update("accounts", acc["id"], {"balance": acc["balance"] + pnl - fees})
        return self.get_trade(trade_id)

    def list_trades(
        self, *, account: str | int | None = None, since: str | None = None,
        symbol: str | None = None, limit: int = 500, open_only: bool = False,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM trades WHERE 1=1"
        params: list[Any] = []
        acc = self.get_account(account) if account is not None else None
        if acc:
            sql += " AND account_id = ?"
            params.append(acc["id"])
        if since:
            sql += " AND opened_at >= ?"
            params.append(since)
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol.strip().upper())
        if open_only:
            sql += " AND closed_at IS NULL"
        sql += " ORDER BY opened_at DESC LIMIT ?"
        params.append(limit)
        return self.db.query(sql, params)

    # ------------------------------------------------------------ auswertung
    def stats(
        self, *, account: str | int | None = None, days: int | None = None
    ) -> dict[str, Any]:
        acc = self.get_account(account)
        since = (date.today() - timedelta(days=days)).isoformat() if days else None
        trades = self.list_trades(account=acc["id"] if acc else None, since=since, limit=5000)
        result = stats_mod.compute_stats(trades, start_balance=float(acc["start_balance"]) if acc else 0.0)
        result["account"] = acc["name"] if acc else "alle"
        result["period_days"] = days
        return result

    def breakdown(self, *, account: str | int | None = None, days: int | None = 90) -> dict[str, Any]:
        acc = self.get_account(account)
        since = (date.today() - timedelta(days=days)).isoformat() if days else None
        trades = self.list_trades(account=acc["id"] if acc else None, since=since, limit=5000)
        return {
            "symbol": stats_mod.by_symbol(trades),
            "setup": stats_mod.by_setup(trades),
            "weekday": stats_mod.by_weekday(trades),
            "hour": stats_mod.by_hour(trades),
            "leaks": stats_mod.find_leaks(trades),
        }

    def realized_today(self, *, account: str | int | None = None, day: str | None = None) -> float:
        acc = self.get_account(account)
        day = day or date.today().isoformat()
        sql = "SELECT COALESCE(SUM(pnl - fees), 0) AS total FROM trades WHERE closed_at LIKE ?"
        params: list[Any] = [f"{day}%"]
        if acc:
            sql += " AND account_id = ?"
            params.append(acc["id"])
        row = self.db.one(sql, params)
        return float(row["total"]) if row else 0.0

    def guard(self, *, account: str | int | None = None, day: str | None = None) -> PropGuard | None:
        acc = self.get_account(account)
        if not acc:
            return None
        realized = self.realized_today(account=acc["id"], day=day)
        return PropGuard(
            account=acc["name"],
            balance=float(acc["balance"]),
            start_balance=float(acc["start_balance"]),
            daily_start_balance=float(acc["balance"]) - realized,
            max_daily_loss_pct=float(acc["max_daily_loss_pct"]),
            max_total_loss_pct=float(acc["max_total_loss_pct"]),
            profit_target_pct=float(acc["profit_target_pct"]),
            realized_today=realized,
        )

    def daily_status(self, *, account: str | int | None = None, day: str | None = None) -> dict[str, Any]:
        """Kompakter Tagesstatus - Herzstueck des Morgen-Briefings."""
        day = day or date.today().isoformat()
        acc = self.get_account(account)
        guard = self.guard(account=account, day=day)
        yesterday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        return {
            "day": day,
            "account": acc["name"] if acc else None,
            "balance": round(float(acc["balance"]), 2) if acc else None,
            "currency": acc["currency"] if acc else "",
            "open_trades": self.list_trades(account=account, open_only=True, limit=50),
            "realized_today": round(self.realized_today(account=account, day=day), 2),
            "realized_yesterday": round(self.realized_today(account=account, day=yesterday), 2),
            "guard": guard.to_dict() if guard else None,
            "week": self.stats(account=account, days=7),
        }

    def weekly_review(self, *, account: str | int | None = None) -> dict[str, Any]:
        week = self.stats(account=account, days=7)
        month = self.stats(account=account, days=30)
        breakdown = self.breakdown(account=account, days=30)
        return {"week": week, "month": month, "breakdown": breakdown}
