"""Bounded, idempotent canonical Pokémon Set Value history repair."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from backend.db.clients.supabase_client import supabase


TOLERANCE = Decimal("0.01")
REFRESH_RPC = "refresh_pokemon_set_value_daily_history"
CONSTITUENT_RPC = "get_pokemon_cards_daily_constituents"


def _validate_range(start: str, end: str) -> None:
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("start-date must not be after end-date")


def _date_keys(start: str, end: str) -> List[str]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return [(first + timedelta(days=offset)).isoformat()
            for offset in range((last - first).days + 1)]


def resolve_sets(client: Any, selector: Optional[str], all_sets: bool) -> List[Dict[str, Any]]:
    query = client.table("sets").select("id,canonical_key,name").eq("ready_for_daily_scrape", True)
    if all_sets:
        pass
    else:
        rows = list(query.execute().data or [])
        needle = str(selector or "").strip()
        return [row for row in rows if needle in {str(row.get("id")), str(row.get("canonical_key"))}]
    return list(query.order("canonical_key").execute().data or [])


def reconcile_set_dates(client: Any, sets: Sequence[Dict[str, Any]], start: str, end: str) -> Dict[str, Any]:
    expected_set_dates: List[Dict[str, str]] = []
    reconciled_set_dates: List[Dict[str, str]] = []
    missing_history_rows: List[Dict[str, Any]] = []
    missing_constituent_totals: List[Dict[str, Any]] = []
    numeric_drift_failures: List[Dict[str, Any]] = []
    max_drift = Decimal(0)
    days = _date_keys(start, end)
    for set_row in sets:
        set_id = str(set_row["id"])
        identity = {"canonical_key": set_row.get("canonical_key"), "set_id": set_id}
        expected_set_dates.extend({**identity, "market_date": day} for day in days)
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
        for day in days:
            history_exists, constituents_exist = day in expected, day in totals
            if not history_exists:
                missing_history_rows.append({**identity, "market_date": day,
                                             "constituents_exist": constituents_exist,
                                             "reason": "both_expected_inputs_absent" if not constituents_exist else "history_row_missing"})
            if not constituents_exist:
                missing_constituent_totals.append({**identity, "market_date": day,
                                                   "history_exists": history_exists,
                                                   "reason": "both_expected_inputs_absent" if not history_exists else "constituent_total_missing"})
            if not (history_exists and constituents_exist):
                continue
            drift = abs(totals[day] - expected[day])
            max_drift = max(max_drift, drift)
            if drift > TOLERANCE:
                numeric_drift_failures.append({**identity, "market_date": day,
                                               "cards_total": str(totals[day]),
                                               "set_value": str(expected[day]), "absolute_drift": str(drift)})
                continue
            reconciled_set_dates.append({**identity, "market_date": day})
    # Count failed set/dates, not diagnostic rows. A date absent from both
    # authorities appears in both missing lists but is one failed expectation.
    failure_count = len(expected_set_dates) - len(reconciled_set_dates)
    return {"sets_checked": len(sets), "expected_set_date_count": len(expected_set_dates),
            "reconciled_set_date_count": len(reconciled_set_dates),
            "expected_set_dates": expected_set_dates, "reconciled_set_dates": reconciled_set_dates,
            "missing_history_rows": missing_history_rows,
            "missing_constituent_totals": missing_constituent_totals,
            "numeric_drift_failures": numeric_drift_failures,
            "failure_count": failure_count, "max_absolute_drift": str(max_drift)}


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
    refresh_coverage_failures: List[Dict[str, Any]] = []
    if commit:
        for row in sets:
            result = client.rpc(REFRESH_RPC, {"p_set_id": row["id"], "p_start_date": start,
                                              "p_end_date": end}).execute()
            refreshed = int(result.data or 0)
            refreshed_rows += refreshed
            if refreshed <= 0:
                refresh_coverage_failures.append({"set_id": str(row["id"]),
                                                  "canonical_key": row.get("canonical_key"),
                                                  "reason": "refresh_rpc_returned_zero"})
    after = reconcile_set_dates(client, sets, start, end) if commit else before
    complete_after = (after["failure_count"] == 0
                      and after["reconciled_set_date_count"] == after["expected_set_date_count"])
    commit_ok = complete_after and not refresh_coverage_failures
    return {"mode": "commit" if commit else "dry_run", "start_date": start, "end_date": end,
            "target_set_count": len(sets), "current_standard_history_rows": current_rows,
            "refreshed_rows": refreshed_rows, "refresh_coverage_failures": refresh_coverage_failures,
            "reconciliation_before": before, "reconciliation_after": after,
            "repair_needed": before["failure_count"] > 0,
            # A preview successfully finding drift is a successful preview. Only
            # commit claims that coverage has been repaired.
            "ok": commit_ok if commit else True}


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
