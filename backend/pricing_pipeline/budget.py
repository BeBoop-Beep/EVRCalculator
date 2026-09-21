"""Request-budget authority: <=1000 eBay Browse requests per America/Phoenix day, across every host and restart.

`DbBudgetLedger` (production) reserves each request through the atomic RPC `reserve_ebay_browse_request_v1`, so a
crash/restart or a second host cannot reset or double-spend the counter. `SqliteBudgetLedger` is the single-host
fallback used by tests and offline development. Both expose `reserve()` for `BrowseHTTP`.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from backend.pricing_pipeline.contracts import DAILY_REQUEST_LIMIT, PipelineError, phoenix_day
from backend.scripts.index_fair_value_ebay_evidence_collector import BudgetExhausted


class DbBudgetLedger:
    def __init__(self, client: Any, day: date | None = None, limit: int = DAILY_REQUEST_LIMIT) -> None:
        self.client, self.limit = client, min(limit, DAILY_REQUEST_LIMIT)
        self.day = day or phoenix_day()

    def reserve(self, market_date: str | None = None) -> None:
        try:
            self.client.rpc("reserve_ebay_browse_request_v1", {"p_day": self.day.isoformat(), "p_limit": self.limit}).execute()
        except Exception as exc:  # noqa: BLE001 - PostgREST surfaces the SQL exception text
            if "EBAY_BROWSE_BUDGET_EXHAUSTED" in str(exc):
                raise BudgetExhausted("shared daily Browse request budget exhausted") from exc
            raise PipelineError("BUDGET_AUTHORITY_UNAVAILABLE", str(exc)[:200]) from exc

    def used(self) -> int:
        rows = self.client.table("ebay_browse_request_ledger_v1").select("requests_reserved").eq(
            "budget_day", self.day.isoformat()).limit(1).execute().data or []
        return int(rows[0]["requests_reserved"]) if rows else 0

    def remaining(self) -> int:
        return max(0, self.limit - self.used())


class SqliteBudgetLedger:
    def __init__(self, path: Path, day: date | None = None, limit: int = DAILY_REQUEST_LIMIT) -> None:
        self.path, self.limit, self.day = Path(path), min(limit, DAILY_REQUEST_LIMIT), day or phoenix_day()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.execute("CREATE TABLE IF NOT EXISTS calls (budget_day TEXT PRIMARY KEY, count INTEGER NOT NULL)")
        return conn

    def reserve(self, market_date: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT count FROM calls WHERE budget_day=?", (self.day.isoformat(),)).fetchone()
            count = int(row[0]) if row else 0
            if count >= self.limit:
                raise BudgetExhausted("daily Browse request budget exhausted")
            conn.execute("INSERT INTO calls(budget_day,count) VALUES(?,?) ON CONFLICT(budget_day) DO UPDATE SET count=excluded.count",
                         (self.day.isoformat(), count + 1))

    def used(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT count FROM calls WHERE budget_day=?", (self.day.isoformat(),)).fetchone()
        return int(row[0]) if row else 0

    def remaining(self) -> int:
        return max(0, self.limit - self.used())
