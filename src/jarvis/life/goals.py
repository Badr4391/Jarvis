"""Ziele: messbar, mit Deadline, mit ehrlicher Pace-Rechnung."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from jarvis.storage.db import Database, utcnow

CATEGORIES = ("trading", "geld", "gesundheit", "arbeit", "privat", "general")

# Ziele, die sich selbst aktualisieren: Wert kommt aus dem Trading-Konto.
AUTO_METRICS = ("balance", "profit", "winrate", "trades")


@dataclass
class GoalManager:
    db: Database

    # ------------------------------------------------------------------ CRUD
    def add(
        self,
        title: str,
        *,
        target_value: float | None = None,
        start_value: float = 0.0,
        current_value: float | None = None,
        unit: str = "",
        deadline: str | None = None,
        category: str = "general",
        why: str = "",
        account: str | int | None = None,
        metric: str = "",
    ) -> dict[str, Any]:
        from jarvis.life.manager import parse_when

        account_id = None
        if account is not None:
            row = self.db.one(
                "SELECT id FROM accounts WHERE lower(name) = ? OR id = ?",
                (str(account).strip().lower(), account if str(account).isdigit() else -1),
            )
            account_id = row["id"] if row else None

        goal_id = self.db.insert(
            "goals",
            {
                "title": title.strip(),
                "why": why,
                "category": category if category in CATEGORIES else "general",
                "target_value": target_value,
                "start_value": start_value,
                "current_value": current_value if current_value is not None else start_value,
                "unit": unit,
                "deadline": parse_when(deadline) or deadline,
                "status": "active",
                "account_id": account_id,
                "metric": metric if metric in AUTO_METRICS else "",
                "created_at": utcnow(),
            },
        )
        return self.get(goal_id) or {}

    def get(self, goal_id: int) -> dict[str, Any] | None:
        row = self.db.one("SELECT * FROM goals WHERE id = ?", (goal_id,))
        return self.enrich(row) if row else None

    def find(self, needle: str) -> dict[str, Any] | None:
        row = self.db.one(
            "SELECT * FROM goals WHERE status='active' AND lower(title) LIKE ? ORDER BY id LIMIT 1",
            (f"%{needle.strip().lower()}%",),
        )
        return self.enrich(row) if row else None

    def list(self, *, status: str = "active", category: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM goals WHERE 1=1"
        params: list[Any] = []
        if status and status != "all":
            sql += " AND status = ?"
            params.append(status)
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY (deadline IS NULL), deadline ASC, id ASC"
        return [self.enrich(row) for row in self.db.query(sql, params)]

    def update(self, goal_id: int, **values: Any) -> dict[str, Any] | None:
        allowed = {
            k: v for k, v in values.items()
            if k in ("title", "why", "category", "target_value", "start_value",
                     "current_value", "unit", "deadline", "status", "metric")
            and v is not None
        }
        self.db.update("goals", goal_id, allowed)
        return self.get(goal_id)

    def complete(self, goal_id: int) -> dict[str, Any] | None:
        self.db.update("goals", goal_id, {"status": "done", "done_at": utcnow()})
        return self.get(goal_id)

    def drop(self, goal_id: int) -> None:
        self.db.update("goals", goal_id, {"status": "dropped", "done_at": utcnow()})

    # ----------------------------------------------------------- fortschritt
    def log_progress(self, goal_id: int, value: float, *, note: str = "",
                     day: str | None = None) -> dict[str, Any] | None:
        day = day or date.today().isoformat()
        self.db.insert(
            "goal_log",
            {"goal_id": goal_id, "day": day, "value": value, "note": note, "created_at": utcnow()},
        )
        self.db.update("goals", goal_id, {"current_value": value})
        goal = self.get(goal_id)
        if goal and goal.get("progress_pct") is not None and goal["progress_pct"] >= 100:
            self.complete(goal_id)
            return self.get(goal_id)
        return goal

    def history(self, goal_id: int, *, limit: int = 60) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT day, value, note FROM goal_log WHERE goal_id = ? ORDER BY day DESC, id DESC LIMIT ?",
            (goal_id, limit),
        )
        return list(reversed(rows))

    def sync_auto_goals(self, journal) -> list[dict[str, Any]]:
        """Ziele mit Konto-Metrik aus dem Journal aktualisieren."""
        updated = []
        for row in self.db.query(
            "SELECT * FROM goals WHERE status='active' AND metric != '' AND account_id IS NOT NULL"
        ):
            account = journal.get_account(row["account_id"])
            if not account:
                continue
            metric = row["metric"]
            if metric == "balance":
                value = float(account["balance"])
            elif metric == "profit":
                value = float(account["balance"]) - float(account["start_balance"])
            else:
                stats = journal.stats(account=account["id"])
                value = float(stats["winrate"]) if metric == "winrate" else float(stats["trades"])
            if abs(value - float(row["current_value"] or 0)) < 1e-9:
                continue
            self.log_progress(row["id"], value, note=f"automatisch aus {account['name']}")
            updated.append(self.get(row["id"]) or {})
        return updated

    # -------------------------------------------------------------- ableitung
    @staticmethod
    def enrich(row: dict[str, Any] | None) -> dict[str, Any]:
        """Fortschritt, Tempo und eine ehrliche Einschaetzung anhaengen."""
        if not row:
            return {}
        goal = dict(row)
        target = goal.get("target_value")
        start = float(goal.get("start_value") or 0.0)
        current = float(goal.get("current_value") or 0.0)

        progress = None
        if target is not None and float(target) != start:
            progress = (current - start) / (float(target) - start) * 100.0
            progress = round(max(0.0, min(progress, 999.0)), 1)
        goal["progress_pct"] = progress

        # Ziele koennen auch nach unten gehen (abnehmen, Schulden tilgen).
        # Der Restweg ist immer positiv, bis das Ziel erreicht ist.
        descending = target is not None and float(target) < start
        goal["direction"] = "runter" if descending else "hoch"
        if target is None:
            goal["remaining"] = None
        elif descending:
            goal["remaining"] = round(max(0.0, current - float(target)), 2)
        else:
            goal["remaining"] = round(max(0.0, float(target) - current), 2)

        days_left = None
        deadline = goal.get("deadline")
        if deadline:
            try:
                days_left = (date.fromisoformat(str(deadline)[:10]) - date.today()).days
            except ValueError:
                days_left = None
        goal["days_left"] = days_left

        # Tempo: wie viel pro Tag noch noetig, und liegt man vor oder hinter Plan?
        goal["per_day_needed"] = None
        goal["pace"] = "unbekannt"
        if target is not None and days_left is not None:
            remaining = goal["remaining"] or 0.0
            if remaining <= 0:
                goal["pace"] = "erreicht"
                goal["per_day_needed"] = 0.0
            elif days_left <= 0:
                goal["pace"] = "ueberfaellig"
                goal["per_day_needed"] = round(remaining, 2)
            else:
                goal["per_day_needed"] = round(remaining / days_left, 2)
                elapsed = _elapsed_days(goal)
                if elapsed and progress is not None:
                    expected = elapsed / (elapsed + days_left) * 100.0
                    if progress >= expected + 5:
                        goal["pace"] = "vor Plan"
                    elif progress >= expected - 5:
                        goal["pace"] = "im Plan"
                    else:
                        goal["pace"] = "hinter Plan"
        return goal

    # -------------------------------------------------------------- uebersicht
    def overview(self) -> dict[str, Any]:
        goals = self.list()
        behind = [g for g in goals if g["pace"] in ("hinter Plan", "ueberfaellig")]
        soon = [g for g in goals if g["days_left"] is not None and 0 <= g["days_left"] <= 14]
        return {
            "aktiv": len(goals),
            "ziele": goals,
            "hinter_plan": behind,
            "bald_faellig": soon,
            "erledigt_30_tage": self.db.query(
                "SELECT title, done_at FROM goals WHERE status='done' AND done_at >= ?",
                ((datetime.now() - timedelta(days=30)).isoformat(),),
            ),
        }


def _elapsed_days(goal: dict[str, Any]) -> int | None:
    created = goal.get("created_at")
    if not created:
        return None
    try:
        started = datetime.fromisoformat(str(created).replace("Z", "+00:00")).date()
    except ValueError:
        return None
    return max(1, (date.today() - started).days)
