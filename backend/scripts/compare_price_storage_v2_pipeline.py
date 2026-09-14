"""Read-only three-root Price Storage V2 integration canary.

Never scrapes, stages, publishes, or mutates a snapshot. The canary validates the
production pricing preview, rebuilds the production market-index math using scoped
root values, and dry-runs the real global Set Value snapshot builder with only the
current Standard root points overridden. Legacy shared-history differences are
expected for qualifying subset roots and are reported rather than treated as truth.
Use explicit --calculation-run-id values for live simulator-view parity checks.
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


def _standard_map(rows):
    return {
        str(row["set_id"]): (amount(row["set_value"]), int(row["priced_card_count"]))
        for row in rows if row.get("value_scope") == "standard"
    }


def _published_set_map(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = row.get("payload_json") or {}
    return {str(item.get("setId")): dict(item) for item in payload.get("sets") or [] if item.get("setId")}


def compare(client: Any, *, day: str, calculation_run_ids: list[str] | None = None) -> dict[str, Any]:
    from backend.db.services.pokemon_market_rollout_index import (
        _current_source_rows, _latest_previous_by_key, build_rollout_index_from_inputs,
    )
    from backend.db.services.pokemon_market_rollout_cohort import rollout_transition_set_ids
    from backend.db.services.pokemon_market_index_service import read_index_history
    from backend.db.services.canonical_market_overview import (
        build_canonical_market_overview, resolve_canonical_overview_sets,
    )
    from backend.scripts.build_pokemon_explore_set_value_snapshot import build as build_set_value_snapshot

    day = market_day(day)
    sets = list(client.table("sets").select("id,name,canonical_key,parent_opening_set_id")
                .in_("name", list(CANARIES)).execute().data or [])
    if (len(sets) != len(CANARIES) or {row["name"] for row in sets} != set(CANARIES)
            or any(row.get("parent_opening_set_id") for row in sets)):
        raise ScopeContractError("the three unique canary root sets are required")
    ids = sorted(str(row["id"]) for row in sets)

    children = list(client.table("sets")
                    .select("id,parent_opening_set_id,counts_toward_parent_set_value")
                    .in_("parent_opening_set_id", ids)
                    .eq("counts_toward_parent_set_value", True)
                    .execute().data or [])
    subset_roots = {str(row["parent_opening_set_id"]) for row in children if row.get("parent_opening_set_id")}

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

    legacy_standard = _standard_map(legacy)
    candidate_standard = _standard_map(candidate)
    source_differences = [
        {"setId": root_id,
         "hasQualifyingSubset": root_id in subset_roots,
         "legacy": [str(legacy_standard[root_id][0]), legacy_standard[root_id][1]] if root_id in legacy_standard else None,
         "candidate": [str(candidate_standard[root_id][0]), candidate_standard[root_id][1]] if root_id in candidate_standard else None}
        for root_id in ids
        if legacy_standard.get(root_id) != candidate_standard.get(root_id)
    ]
    unexpected_source_differences = [row for row in source_differences if not row["hasQualifyingSubset"]]

    old_index = build_rollout_index_from_inputs(market_date=day, sets=sets, source_rows=legacy,
                                               previous=previous, transition_ids=transitions)
    new_index = build_rollout_index_from_inputs(market_date=day, sets=sets, source_rows=candidate,
                                               previous=previous, transition_ids=transitions)
    legacy_index_comparison = compare_index_outputs(old_index, new_index)

    # Freeze the full-market overview inputs once, then run the actual Set Value
    # snapshot builder twice. Only the candidate replay receives three current-day
    # Standard root overrides; every other set and every historical point is unchanged.
    market_index_history = read_index_history(client, through_date=day)
    overview_sets = resolve_canonical_overview_sets(client, market_date=day)
    market_overview = build_canonical_market_overview(
        client,
        market_date=day,
        history=market_index_history,
        set_ids=[str(row["id"]) for row in overview_sets],
    )
    legacy_set_value_snapshot = build_set_value_snapshot(
        client=client, market_date=day, commit=False,
        market_index_history=market_index_history, market_overview=market_overview,
    )
    standard_overrides = [row for row in candidate if row.get("value_scope") == "standard"]
    candidate_set_value_snapshot = build_set_value_snapshot(
        client=client, market_date=day, commit=False,
        market_index_history=market_index_history, market_overview=market_overview,
        current_standard_overrides=standard_overrides,
    )
    legacy_published = _published_set_map(legacy_set_value_snapshot)
    candidate_published = _published_set_map(candidate_set_value_snapshot)
    snapshot_canary_results = []
    for root_id in ids:
        expected = candidate_standard[root_id][0]
        row = candidate_published.get(root_id)
        actual = amount(row.get("currentSetValue")) if row else None
        snapshot_canary_results.append({
            "setId": root_id,
            "expectedRootValue": str(expected),
            "candidateSnapshotValue": str(actual) if actual is not None else None,
            "matchesRootPreview": actual == expected,
            "legacySnapshotValue": str(amount(legacy_published[root_id]["currentSetValue"]))
                if root_id in legacy_published else None,
        })
    other_ids = (set(legacy_published) | set(candidate_published)) - set(ids)
    unrelated_snapshot_rows_equal = all(legacy_published.get(key) == candidate_published.get(key) for key in other_ids)
    snapshot_replay_pass = (
        all(row["matchesRootPreview"] for row in snapshot_canary_results)
        and unrelated_snapshot_rows_equal
        and set(legacy_published) == set(candidate_published)
    )

    result = {
        "status": "pass",
        "market_date": day,
        "canaries": list(CANARIES),
        "source_previews_passed": len(previews),
        "qualifying_subset_root_ids": sorted(subset_roots),
        "legacy_shared_history_differences": source_differences,
        "unexpected_legacy_differences": unexpected_source_differences,
        "legacy_index_economic_comparison": legacy_index_comparison,
        "candidate_index_rows": len(new_index),
        "set_value_snapshot_replay": {
            "status": "pass" if snapshot_replay_pass else "blocked",
            "canaries": snapshot_canary_results,
            "unrelated_set_rows_equal": unrelated_snapshot_rows_equal,
            "legacy_set_count": len(legacy_published),
            "candidate_set_count": len(candidate_published),
            "publication_performed": False,
        },
        "publication_authorized": False,
    }

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
    result["persisted_snapshot_payloads"] = {table: {
        "before_rows": len(before[table]), "after_rows": len(after[table]),
        "unchanged": bool(before[table]) and digest(before[table]) == digest(after[table]),
        "before_sha256": digest(before[table]), "after_sha256": digest(after[table]),
    } for table in SNAPSHOTS}
    repeated = {root_id: client.rpc(PREVIEW_RPC, {"p_root_set_id": root_id, "p_market_date": day})
                .execute().data for root_id in ids}
    result["inputs_stable_during_comparison"] = (
        previews == repeated
        and digest(legacy) == digest(_current_source_rows(client, ids, day))
        and previous == _latest_previous_by_key(client, day)
        and set(transitions) == set(rollout_transition_set_ids(client, day))
    )
    result["full_snapshot_builder_replay"] = "pass" if snapshot_replay_pass else "blocked"
    result["full_end_to_end_pass"] = False  # no scrape/stage/publish/write is performed by this canary

    if (unexpected_source_differences
            or not snapshot_replay_pass
            or not result["inputs_stable_during_comparison"]
            or simulation["status"] == "blocked"
            or not all(row["unchanged"] for row in result["persisted_snapshot_payloads"].values())):
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
        report = {"status": "blocked", "error_type": type(exc).__name__, "publication_authorized": False}
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())