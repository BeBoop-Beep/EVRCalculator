"""Read-only three-root canary. Never scrapes, simulates, stages, or publishes.

Runs the production index math twice with the same cohort/prior index rows.
A pass covers source/index compatibility, NOT a full snapshot-builder replay.
Use explicit --calculation-run-id values to compare frozen/current simulator views.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.services.price_storage_v2_integration import (
    PREVIEW_RPC, ScopeContractError, amount, compare_index_outputs, market_day, root_source_rows,
)

CANARIES = ("Evolving Skies", "Crown Zenith", "Celebrations")
SNAPSHOTS = ("pokemon_set_page_snapshot_latest", "pokemon_set_market_dashboard_snapshot_latest")


def digest(rows: list[dict[str, Any]]) -> str:
    # Stable across PostgREST row order; includes complete selected payloads.
    encoded = sorted(json.dumps(row, sort_keys=True, default=str, separators=(",", ":")) for row in rows)
    return hashlib.sha256("\n".join(encoded).encode()).hexdigest()


def paged(query: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for start in range(0, 100_000, 500):
        page = list(query.range(start, start + 499).execute().data or [])
        rows.extend(page)
        if len(page) < 500:
            return rows
    raise ScopeContractError("bounded canary row limit exceeded; refusing a truncated comparison")


def compare(client: Any, *, day: str, calculation_run_ids: list[str] | None = None) -> dict[str, Any]:
    from backend.db.services.pokemon_market_rollout_index import (
        _current_source_rows, _latest_previous_by_key, build_rollout_index_from_inputs,
    )
    from backend.db.services.pokemon_market_rollout_cohort import rollout_transition_set_ids
    day = market_day(day)
    sets = list(client.table("sets").select("id,name,canonical_key,parent_opening_set_id")
                .in_("name", list(CANARIES)).execute().data or [])
    if (len(sets) != len(CANARIES) or {row["name"] for row in sets} != set(CANARIES)
            or any(row.get("parent_opening_set_id") for row in sets)):
        raise ScopeContractError("the three unique canary root sets are required")
    ids = sorted(str(row["id"]) for row in sets)

    def snapshots():
        return {table: paged(client.table(table).select("*").in_("set_id", ids)
                             .order("set_id").order("window_key") if table.endswith("dashboard_snapshot_latest")
                             else client.table(table).select("*").in_("set_id", ids).order("set_id"))
                for table in SNAPSHOTS}

    before = snapshots()
    legacy = _current_source_rows(client, ids, day)
    previous = _latest_previous_by_key(client, day)
    transitions = rollout_transition_set_ids(client, day)
    previews = {row["id"]: client.rpc(PREVIEW_RPC, {"p_root_set_id": row["id"], "p_market_date": day})
                .execute().data for row in sets}
    candidate = [source for root_id in ids for source in root_source_rows(previews[root_id], root_id, day)]
    old_index = build_rollout_index_from_inputs(market_date=day, sets=sets, source_rows=legacy,
                                              previous=previous, transition_ids=transitions)
    new_index = build_rollout_index_from_inputs(market_date=day, sets=sets, source_rows=candidate,
                                              previous=previous, transition_ids=transitions)
    result = compare_index_outputs(old_index, new_index)
    result["market_date"] = day
    result["canaries"] = list(CANARIES)
    result["index_comparison_is_diagnostic_subcohort"] = True
    result["source_previews_passed"] = len(previews)
    result["source_rows_equal"] = sorted(
        (r["set_id"], r["value_scope"], amount(r["set_value"]), r["priced_card_count"])
        for r in legacy if r["value_scope"] in {"standard", "top10"}
    ) == sorted(
        (r["set_id"], r["value_scope"], amount(r["set_value"]), r["priced_card_count"])
        for r in candidate if r["value_scope"] in {"standard", "top10"}
    )
    simulation = {"status": "not_run", "reason": "explicit calculation-run IDs were not supplied"}
    if calculation_run_ids:
        if len(calculation_run_ids) > 22 or len(set(calculation_run_ids)) != len(calculation_run_ids):
            raise ScopeContractError("provide at most 22 distinct calculation-run IDs")
        views = ("simulation_input_cards_with_near_mint_price_legacy_shadow",
                 "simulation_input_cards_with_near_mint_price")
        data = [paged(client.table(view).select("*").in_("calculation_run_id", calculation_run_ids)
                      .order("id")) for view in views]
        complete = all({r["calculation_run_id"] for r in rows} == set(calculation_run_ids) for rows in data)
        simulation = {"status": "pass" if complete and digest(data[0]) == digest(data[1]) else "blocked",
                      "legacy_rows": len(data[0]), "v2_rows": len(data[1]), "all_requested_runs_present": complete}
    result["simulation_reader_comparison"] = simulation
    after = snapshots()
    result["snapshot_payloads"] = {table: {
        "before_rows": len(before[table]), "after_rows": len(after[table]),
        "unchanged": bool(before[table]) and digest(before[table]) == digest(after[table]),
        "before_sha256": digest(before[table]), "after_sha256": digest(after[table]),
    } for table in SNAPSHOTS}
    repeated = {root_id: client.rpc(PREVIEW_RPC, {"p_root_set_id": root_id, "p_market_date": day})
                .execute().data for root_id in ids}
    result["inputs_stable_during_comparison"] = (previews == repeated and digest(legacy) == digest(_current_source_rows(client, ids, day))
        and previous == _latest_previous_by_key(client, day)
        and set(transitions) == set(rollout_transition_set_ids(client, day)))
    result["full_snapshot_builder_replay"] = "not_run"
    result["full_end_to_end_pass"] = False
    if (not result["source_rows_equal"] or not result["inputs_stable_during_comparison"]
            or simulation["status"] == "blocked"
            or not all(row["unchanged"] for row in result["snapshot_payloads"].values())):
        result["status"] = "blocked"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", required=True)
    parser.add_argument("--calculation-run-id", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from backend.scripts.pokemon_snapshot_builders import get_client
    try:
        report = compare(get_client(), day=args.market_date, calculation_run_ids=args.calculation_run_id)
    except Exception as exc:
        # Do not print database/client exception messages that may contain credentials.
        report = {"status": "blocked", "error_type": type(exc).__name__, "publication_authorized": False}
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
