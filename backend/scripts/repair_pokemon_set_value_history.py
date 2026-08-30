"""Bounded, idempotent canonical Pokémon Set Value history repair."""

from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from backend.db.clients.supabase_client import supabase


TOLERANCE = Decimal("0.01")
REFRESH_RPC = "refresh_pokemon_set_value_daily_history"
CONSTITUENT_RPC = "get_pokemon_cards_daily_constituents"


def _validate_range(start: str, end: str) -> None:
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("start-date must not be after end-date")


def resolve_sets(client: Any, selector: Optional[str], all_sets: bool) -> List[Dict[str, Any]]:
    query = client.table("sets").select("id,canonical_key,name")
    if all_sets:
        query = query.eq("ready_for_daily_scrape", True)
    else:
        rows = list(query.execute().data or [])
        needle = str(selector or "").strip()
        return [row for row in rows if needle in {str(row.get("id")), str(row.get("canonical_key"))}]
    return list(query.order("canonical_key").execute().data or [])


def reconcile_set_dates(client: Any, sets: Sequence[Dict[str, Any]], start: str, end: str) -> Dict[str, Any]:
    failures, checked, max_drift = [], 0, Decimal(0)
    for set_row in sets:
        set_id = str(set_row["id"])
        history = list((client.table("pokemon_set_value_daily_history")
                        .select("snapshot_date,set_value").eq("set_id", set_id)
                        .eq("value_scope", "standard").gte("snapshot_date", start)
                        .lte("snapshot_date", end).order("snapshot_date").execute()).data or [])
        expected = {str(row["snapshot_date"])[:10]: Decimal(str(row["set_value"])) for row in history}
        rows = list(client.rpc(CONSTITUENT_RPC, {
            "p_set_ids": [set_id], "p_start_date": start, "p_end_date": end, "p_card_ids": None,
        }).execute().data or [])
        totals: Dict[str, Decimal] = {}
        for row in rows:
            day = str(row["market_date"])[:10]
            totals[day] = totals.get(day, Decimal(0)) + Decimal(str(row["market_price"]))
        for day in sorted(expected.keys() & totals.keys()):
            checked += 1
            drift = abs(totals[day] - expected[day])
            max_drift = max(max_drift, drift)
            if drift > TOLERANCE:
                failures.append({"canonical_key": set_row.get("canonical_key"), "set_id": set_id,
                                 "market_date": day, "cards_total": str(totals[day]),
                                 "set_value": str(expected[day]), "absolute_drift": str(drift)})
    return {"sets_checked": len(sets), "set_dates_checked": checked,
            "failure_count": len(failures), "max_absolute_drift": str(max_drift), "failures": failures}


def repair_history(client: Any, *, start: str, end: str, selector: Optional[str],
                   all_sets: bool, commit: bool) -> Dict[str, Any]:
    _validate_range(start, end)
    sets = resolve_sets(client, selector, all_sets)
    if not sets:
        raise ValueError("no matching scrape-ready Pokémon sets")
    current_rows = 0
    for row in sets:
        result = (client.table("pokemon_set_value_daily_history").select("set_id", count="exact")
                  .eq("set_id", row["id"]).eq("value_scope", "standard")
                  .gte("snapshot_date", start).lte("snapshot_date", end).execute())
        current_rows += int(getattr(result, "count", None) or len(result.data or []))
    before = reconcile_set_dates(client, sets, start, end)
    refreshed_rows = 0
    if commit:
        for row in sets:
            result = client.rpc(REFRESH_RPC, {"p_set_id": row["id"], "p_start_date": start,
                                              "p_end_date": end}).execute()
            refreshed_rows += int(result.data or 0)
    after = reconcile_set_dates(client, sets, start, end) if commit else before
    return {"mode": "commit" if commit else "dry_run", "start_date": start, "end_date": end,
            "target_set_count": len(sets), "current_standard_history_rows": current_rows,
            "refreshed_rows": refreshed_rows, "reconciliation_before": before,
            "reconciliation_after": after, "ok": after["failure_count"] == 0}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--set")
    scope.add_argument("--all", action="store_true")
    parser.add_argument("--commit", action="store_true", help="Write via canonical refresh RPC; default is dry-run")
    args = parser.parse_args(argv)
    try:
        report = repair_history(supabase, start=args.start_date, end=args.end_date,
                                selector=args.set, all_sets=args.all, commit=args.commit)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
