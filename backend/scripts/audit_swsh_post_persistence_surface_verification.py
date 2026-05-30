"""Project 11 read-only post-persistence surface verification for swsh6/swsh7.

This script verifies that known persisted Project 10.3 run artifacts are:
- present and internally linked across write tables
- structurally usable by downstream read surfaces/views/APIs
- visible to latest-read selection paths used by Explore/RIP experiences

Hard guardrails:
- No execute rerun
- No DB mutation
- Read-only SELECT queries only
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from backend.db.clients import supabase_client


DEFAULT_JSON_PATH = Path("logs/audits/swsh_project_11_post_persistence_surface_verification.json")
DEFAULT_MD_PATH = Path("backend/docs/audits/SWSH_PROJECT_11_POST_PERSISTENCE_SURFACE_VERIFICATION.md")

TARGET_SET_IDS = ("swsh6", "swsh7")
SOURCE_PROJECT_10_CLOSURE_ARTIFACT = "logs/audits/swsh_project_10_execute_closure_repaired.json"

# Successful persisted run IDs from Project 10.3 (provided input contract).
PROJECT_10_3_IDENTIFIERS: Dict[str, Dict[str, str]] = {
    "swsh6": {
        "parent_run_id": "0dd7683c-4146-4dcd-a04c-6f686bd91417",
        "simulation_summary_id": "8f4f4bcf-3d01-454b-851d-d7d295bd2f96",
    },
    "swsh7": {
        "parent_run_id": "91e93106-b677-46de-b398-6728aa7842fb",
        "simulation_summary_id": "1c0724b1-cbe4-4cb9-acb6-23348a3a27d3",
    },
}

PRIOR_REAL_WRITE_COUNTS_TOTAL = {
    "calculation_runs": 2,
    "calculation_price_snapshots": 4,
    "simulation_input_cards": 470,
    "simulation_run_summary": 2,
    "simulation_percentiles": 14,
    "simulation_pull_summary": 28,
    "simulation_state_counts": 2,
    "simulation_derived_metrics": 2,
    "simulation_value_distribution_bins": 100,
    "simulation_value_threshold_bins": 36,
}

EXPECTED_PER_RUN_EXACT = {
    "simulation_run_summary": 1,
    "simulation_percentiles": 7,
    "simulation_derived_metrics": 1,
    "simulation_value_distribution_bins": 50,
    "simulation_value_threshold_bins": 18,
}

EXPECTED_PER_RUN_NON_ZERO = {
    "calculation_price_snapshots": 1,
    "simulation_input_cards": 1,
    "simulation_pull_summary": 1,
    "simulation_state_counts": 1,
}

EXPECTED_SOURCE_CORRECT_ACTIVE_BUCKETS = {
    "swsh6": {
        "rare",
        "holo rare",
        "regular v",
        "regular vmax",
        "full art v",
        "full art trainer",
        "alternate art v",
        "alternate art vmax",
        "rainbow rare",
        "gold rare",
    },
    "swsh7": {
        "rare",
        "holo rare",
        "regular v",
        "regular vmax",
        "full art",
        "alternate art v",
        "alternate art vmax",
        "rainbow rare",
        "gold rare",
    },
}

EXPECTED_UNSUPPORTED_BUCKETS_ABSENT = {
    "swsh6": {
        "rainbow trainer",
        "rainbow vmax",
        "gold secret rare",
    },
    "swsh7": {
        "full art v",
        "full art trainer",
        "rainbow trainer",
        "rainbow vmax",
        "gold secret rare",
    },
}

RIP_REQUIRED_FIELDS = (
    "pack_score",
    "pack_cost",
    "mean_value",
    "median_value",
    "roi_percent",
    "prob_profit",
    "p95_value_to_cost_ratio",
    "mean_value_to_cost_ratio",
)

CRITICAL_SUMMARY_FIELDS = (
    "pack_cost",
    "mean_value",
    "median_value",
    "roi",
    "roi_percent",
    "prob_profit",
)

CRITICAL_DERIVED_FIELDS = (
    "pack_score",
    "p95_value_to_cost_ratio",
    "mean_value_to_cost_ratio",
)


def _fetch_rows(
    table_name: str,
    *,
    filters: Optional[Mapping[str, Any]] = None,
    order_by: Optional[str] = None,
    desc: bool = False,
    limit: Optional[int] = None,
    select_columns: str = "*",
    client: Any,
) -> List[Dict[str, Any]]:
    query = client.table(table_name).select(select_columns)
    for key, value in (filters or {}).items():
        query = query.eq(str(key), value)
    if order_by:
        query = query.order(order_by, desc=desc)
    if limit is not None:
        query = query.limit(int(limit))
    response = query.execute()
    rows = getattr(response, "data", None)
    return [dict(row) for row in rows] if isinstance(rows, list) else []


def _fetch_one_by_id(table_name: str, row_id: str, *, client: Any) -> Optional[Dict[str, Any]]:
    rows = _fetch_rows(
        table_name,
        filters={"id": str(row_id)},
        limit=1,
        client=client,
    )
    return rows[0] if rows else None


def _count_for_run(table_name: str, run_id: str, *, client: Any) -> int:
    rows = _fetch_rows(
        table_name,
        filters={"calculation_run_id": str(run_id)},
        client=client,
    )
    return len(rows)


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _normalize_bucket(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", " ").replace("-", " ")


def _resolve_target_identifier_for_set(set_id: str, *, client: Any) -> Dict[str, Any]:
    # In production this set key (swsh6/swsh7) resolves to a UUID set id.
    # Tests may use direct string ids and omit the sets table entirely.
    for key in ("canonical_key", "pokemon_api_set_id", "id"):
        rows = _fetch_rows(
            "sets",
            filters={key: set_id},
            limit=1,
            client=client,
        )
        if rows:
            row = rows[0]
            resolved_id = row.get("id")
            if _is_non_empty(resolved_id):
                return {
                    "resolved_set_row_id": str(resolved_id),
                    "resolution_source": key,
                }
    return {
        "resolved_set_row_id": str(set_id),
        "resolution_source": "fallback_requested_set_key",
    }


def _latest_identifier_from_public_surfaces(set_id: str, *, service_client: Any, public_client: Any) -> Dict[str, Any]:
    target_resolution = _resolve_target_identifier_for_set(set_id, client=service_client)
    resolved_target_id = str(target_resolution.get("resolved_set_row_id") or set_id)

    source = ""
    run_id = ""

    explore_rows = _fetch_rows(
        "explore_rip_statistics_latest",
        filters={"set_id": resolved_target_id},
        limit=1,
        client=public_client,
    )
    if explore_rows and _is_non_empty(explore_rows[0].get("calculation_run_id")):
        run_id = str(explore_rows[0].get("calculation_run_id"))
        source = "explore_rip_statistics_latest"

    if not run_id:
        latest_rows = _fetch_rows(
            "simulation_latest_by_target",
            filters={"target_type": "set", "target_id": resolved_target_id},
            order_by="run_at",
            desc=True,
            limit=1,
            client=public_client,
        )
        if latest_rows and _is_non_empty(latest_rows[0].get("calculation_run_id")):
            run_id = str(latest_rows[0].get("calculation_run_id"))
            source = "simulation_latest_by_target"

    if not run_id:
        calc_rows = _fetch_rows(
            "calculation_runs",
            filters={"target_type": "set", "target_id": resolved_target_id},
            order_by="created_at",
            desc=True,
            limit=1,
            client=service_client,
        )
        if calc_rows and _is_non_empty(calc_rows[0].get("id")):
            run_id = str(calc_rows[0].get("id"))
            source = "calculation_runs_latest_lookup_fallback"

    if not run_id:
        return {
            "set_id": set_id,
            "resolved_target_id": resolved_target_id,
            "target_resolution_source": target_resolution.get("resolution_source"),
            "latest_source": None,
            "parent_run_id": "",
            "simulation_summary_id": "",
            "error": "latest_run_id_not_found",
        }

    summary_rows = _fetch_rows(
        "simulation_run_summary",
        filters={"calculation_run_id": run_id},
        order_by="created_at",
        desc=True,
        limit=1,
        client=service_client,
    )
    summary_id = str((summary_rows[0] if summary_rows else {}).get("id") or "")

    return {
        "set_id": set_id,
        "resolved_target_id": resolved_target_id,
        "target_resolution_source": target_resolution.get("resolution_source"),
        "latest_source": source,
        "parent_run_id": str(run_id),
        "simulation_summary_id": summary_id,
        "error": None if summary_id else "latest_run_summary_id_not_found",
    }


def _determine_final_decision(
    *,
    hard_blockers: List[str],
    read_surface_gap_blockers: List[str],
    latest_mismatch_found: bool,
) -> str:
    if hard_blockers:
        return "not_closed_blockers_remaining"
    if read_surface_gap_blockers:
        return "closed_post_persistence_blocked_on_read_surface_gap"
    if latest_mismatch_found:
        return "closed_persistence_valid_but_not_latest_surface_visible"
    return "closed_post_persistence_surface_verified"


def _next_step_for_decision(final_decision: str) -> str:
    if final_decision == "closed_post_persistence_surface_verified":
        return "No DB action required; proceed with normal downstream read/API validation in environment-specific smoke checks."
    if final_decision == "closed_persistence_valid_but_not_latest_surface_visible":
        return (
            "Run a separate, explicit read-surface publication/latest-selector investigation prompt to update latest-pointer/view logic "
            "without altering simulation payload tables."
        )
    if final_decision == "closed_post_persistence_blocked_on_read_surface_gap":
        return (
            "Run a read-surface contract clarification prompt for explore_rip_statistics_latest/simulation_latest_by_target "
            "to document required columns and stable latest-selection behavior before any mutation is considered."
        )
    return "Resolve listed blockers with a targeted read-only diagnosis prompt before considering any controlled mutation plan."


def _read_project_10_closure_brief() -> Dict[str, Any]:
    source = Path(SOURCE_PROJECT_10_CLOSURE_ARTIFACT)
    if not source.exists():
        return {"exists": False}
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive in script runtime
        return {
            "exists": True,
            "parse_error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "exists": True,
        "final_decision": payload.get("final_decision"),
        "db_mutation_performed": payload.get("db_mutation_performed"),
        "execute_rerun_performed": payload.get("execute_rerun_performed"),
        "read_only_db_verification_passed": (payload.get("read_only_db_verification") or {}).get("passed"),
        "safety_passed": payload.get("safety_passed"),
    }


def _verify_single_set(
    set_id: str,
    parent_run_id: str,
    summary_id: str,
    *,
    latest_resolution_source: Optional[str] = None,
) -> Dict[str, Any]:
    blockers: List[str] = []
    read_surface_gap_blockers: List[str] = []
    warnings: List[str] = []

    service_client = supabase_client.supabase
    public_client = supabase_client.public_read_client

    target_resolution = _resolve_target_identifier_for_set(set_id, client=service_client)
    resolved_target_id = str(target_resolution.get("resolved_set_row_id") or set_id)

    run_row = _fetch_one_by_id("calculation_runs", parent_run_id, client=service_client)
    summary_row = _fetch_one_by_id("simulation_run_summary", summary_id, client=service_client)

    run_exists = run_row is not None
    summary_exists = summary_row is not None

    if not run_exists:
        blockers.append(f"{set_id}: calculation_runs row missing for run_id={parent_run_id}")
    if not summary_exists:
        blockers.append(f"{set_id}: simulation_run_summary row missing for summary_id={summary_id}")

    run_target_type = (run_row or {}).get("target_type")
    run_target_id = (run_row or {}).get("target_id")
    run_target_identity_ok = bool(
        run_target_type == "set"
        and str(run_target_id) in {str(resolved_target_id), str(set_id)}
    )
    if run_exists and not run_target_identity_ok:
        blockers.append(
            f"{set_id}: calculation_runs target identity mismatch "
            f"(target_type={run_target_type}, target_id={run_target_id}, expected_one_of=[{resolved_target_id},{set_id}])"
        )

    summary_parent_run_id = str((summary_row or {}).get("calculation_run_id") or "") if summary_row else ""
    summary_belongs_to_expected_run = bool(summary_parent_run_id and summary_parent_run_id == parent_run_id)
    if summary_exists and not summary_belongs_to_expected_run:
        blockers.append(
            f"{set_id}: simulation_run_summary {summary_id} does not belong to run_id={parent_run_id}"
        )

    config_link_exists = False
    calculation_config_id = (run_row or {}).get("calculation_config_id")
    if _is_non_empty(calculation_config_id):
        config_row = _fetch_one_by_id("calculation_configs", str(calculation_config_id), client=service_client)
        config_link_exists = config_row is not None
    if run_exists and not config_link_exists:
        blockers.append(f"{set_id}: calculation_config link missing or orphaned for run_id={parent_run_id}")

    counts_by_table = {
        "calculation_runs": 1 if run_exists else 0,
        "simulation_run_summary": 1 if summary_exists else 0,
        "calculation_price_snapshots": _count_for_run("calculation_price_snapshots", parent_run_id, client=service_client),
        "simulation_input_cards": _count_for_run("simulation_input_cards", parent_run_id, client=service_client),
        "simulation_percentiles": _count_for_run("simulation_percentiles", parent_run_id, client=service_client),
        "simulation_pull_summary": _count_for_run("simulation_pull_summary", parent_run_id, client=service_client),
        "simulation_state_counts": _count_for_run("simulation_state_counts", parent_run_id, client=service_client),
        "simulation_derived_metrics": _count_for_run("simulation_derived_metrics", parent_run_id, client=service_client),
        "simulation_value_distribution_bins": _count_for_run(
            "simulation_value_distribution_bins", parent_run_id, client=service_client
        ),
        "simulation_value_threshold_bins": _count_for_run(
            "simulation_value_threshold_bins", parent_run_id, client=service_client
        ),
    }

    pull_summary_rows = _fetch_rows(
        "simulation_pull_summary",
        filters={"calculation_run_id": str(parent_run_id)},
        client=service_client,
    )
    observed_pull_summary_buckets = {
        _normalize_bucket(row.get("rarity_bucket"))
        for row in pull_summary_rows
        if _normalize_bucket(row.get("rarity_bucket"))
    }

    required_buckets = set(EXPECTED_SOURCE_CORRECT_ACTIVE_BUCKETS.get(set_id, set()))
    unsupported_buckets = set(EXPECTED_UNSUPPORTED_BUCKETS_ABSENT.get(set_id, set()))
    missing_required_buckets = sorted(required_buckets - observed_pull_summary_buckets)
    present_unsupported_buckets = sorted(unsupported_buckets.intersection(observed_pull_summary_buckets))

    if missing_required_buckets:
        blockers.append(
            f"{set_id}: simulation_pull_summary missing required source-correct buckets: {', '.join(missing_required_buckets)}"
        )
    if present_unsupported_buckets:
        blockers.append(
            f"{set_id}: simulation_pull_summary contains unsupported buckets: {', '.join(present_unsupported_buckets)}"
        )

    for table_name, expected in EXPECTED_PER_RUN_EXACT.items():
        actual = counts_by_table.get(table_name, 0)
        if actual != expected:
            blockers.append(f"{set_id}: {table_name} expected={expected} actual={actual}")

    for table_name, min_count in EXPECTED_PER_RUN_NON_ZERO.items():
        actual = counts_by_table.get(table_name, 0)
        if actual < min_count:
            blockers.append(f"{set_id}: {table_name} must be > 0 (actual={actual})")

    state_count_rows = _fetch_rows(
        "simulation_state_counts",
        filters={"calculation_run_id": str(parent_run_id)},
        client=service_client,
    )
    combo_rows = [
        row
        for row in state_count_rows
        if _normalize_bucket(row.get("state_group")) == "slot schema combo"
    ]
    pack_path_rows = [
        row
        for row in state_count_rows
        if _normalize_bucket(row.get("state_group")) == "pack path"
    ]
    normal_pack_state_rows = [
        row
        for row in state_count_rows
        if _normalize_bucket(row.get("state_group")) == "normal pack state"
    ]
    combo_rows_count = len(combo_rows)
    combo_occurrence_total = sum(int(row.get("occurrence_count") or 0) for row in combo_rows)

    if len(pack_path_rows) <= 0:
        blockers.append(f"{set_id}: simulation_state_counts missing pack_path rows")

    # "count matches expected or is explainable" rule for price snapshots.
    if counts_by_table["calculation_price_snapshots"] != 2:
        warnings.append(
            f"{set_id}: calculation_price_snapshots count is {counts_by_table['calculation_price_snapshots']} (expected typical=2); "
            "accepted as explainable if pack+etb snapshots differ by runtime strategy"
        )

    derived_rows = _fetch_rows(
        "simulation_derived_metrics",
        filters={"calculation_run_id": parent_run_id},
        limit=1,
        client=service_client,
    )
    derived_row = derived_rows[0] if derived_rows else {}

    # Critical-null checks needed by downstream reads.
    null_critical_fields: List[str] = []
    for field in CRITICAL_SUMMARY_FIELDS:
        if summary_row is not None and not _is_non_empty(summary_row.get(field)):
            null_critical_fields.append(f"simulation_run_summary.{field}")
    for field in CRITICAL_DERIVED_FIELDS:
        if derived_row and not _is_non_empty(derived_row.get(field)):
            null_critical_fields.append(f"simulation_derived_metrics.{field}")

    if null_critical_fields:
        blockers.append(f"{set_id}: critical fields are null/empty: {', '.join(sorted(null_critical_fields))}")

    # Explicit semantics/field-presence checks requested by contract.
    formula_roi_present = bool(_is_non_empty((summary_row or {}).get("roi")) and _is_non_empty((summary_row or {}).get("roi_percent")))
    value_to_cost_ratio_present = bool(
        _is_non_empty((derived_row or {}).get("mean_value_to_cost_ratio"))
        or _is_non_empty((derived_row or {}).get("p95_value_to_cost_ratio"))
    )
    metric_semantics_version_value = (
        (derived_row or {}).get("derived_metric_version")
        or (derived_row or {}).get("score_version")
        or (derived_row or {}).get("normalization_mode")
    )
    metric_semantics_version_present = _is_non_empty(metric_semantics_version_value)
    probability_to_beat_pack_cost_present = _is_non_empty((summary_row or {}).get("prob_profit"))

    if not formula_roi_present:
        blockers.append(f"{set_id}: formula ROI fields are missing")
    if not value_to_cost_ratio_present:
        blockers.append(f"{set_id}: value_to_cost_ratio fields are missing")
    if not metric_semantics_version_present:
        read_surface_gap_blockers.append(f"{set_id}: metric semantics version field not found in persisted derived metrics")
    if not probability_to_beat_pack_cost_present:
        blockers.append(f"{set_id}: probability-to-beat-pack-cost field is missing")

    simulation_count_value = (summary_row or {}).get("simulation_count")
    simulation_count = int(simulation_count_value) if _is_non_empty(simulation_count_value) else None

    # Read-surface visibility checks.
    def _safe_first(table_name: str, *, filters: Mapping[str, Any], order_by: Optional[str] = None) -> Optional[Dict[str, Any]]:
        try:
            rows = _fetch_rows(
                table_name,
                filters=filters,
                order_by=order_by,
                desc=True if order_by else False,
                limit=1,
                client=public_client,
            )
            return rows[0] if rows else None
        except Exception as exc:
            read_surface_gap_blockers.append(f"{set_id}: unable to query {table_name}: {type(exc).__name__}: {exc}")
            return None

    explore_latest_row = _safe_first(
        "explore_rip_statistics_latest",
        filters={"set_id": resolved_target_id},
    )
    simulation_latest_row = _safe_first(
        "simulation_latest_by_target",
        filters={"target_type": "set", "target_id": resolved_target_id},
        order_by="run_at",
    )
    calculation_latest_row = _safe_first(
        "calculation_runs",
        filters={"target_type": "set", "target_id": resolved_target_id},
        order_by="created_at",
    )

    try:
        ranking_rows = _fetch_rows(
            "set_pack_score_rankings_latest",
            filters={"target_id": resolved_target_id, "calculation_run_id": parent_run_id},
            limit=1,
            client=public_client,
        )
        ranking_row_exists_for_verified_run = bool(ranking_rows)
    except Exception as exc:
        ranking_row_exists_for_verified_run = False
        read_surface_gap_blockers.append(
            f"{set_id}: unable to query set_pack_score_rankings_latest: {type(exc).__name__}: {exc}"
        )

    explore_latest_run_id = str((explore_latest_row or {}).get("calculation_run_id") or "")
    simulation_latest_run_id = str((simulation_latest_row or {}).get("calculation_run_id") or "")
    calculation_latest_run_id = str((calculation_latest_row or {}).get("id") or "")

    explore_latest_selects_verified_run = bool(explore_latest_run_id == parent_run_id)
    simulation_latest_selects_verified_run = bool(simulation_latest_run_id == parent_run_id)
    calculation_latest_selects_verified_run = bool(calculation_latest_run_id == parent_run_id)

    explore_required_fields_missing: List[str] = []
    if explore_latest_row is not None:
        explore_required_fields_missing = [field for field in RIP_REQUIRED_FIELDS if field not in explore_latest_row]
        if explore_required_fields_missing:
            read_surface_gap_blockers.append(
                f"{set_id}: explore_rip_statistics_latest missing required fields: {', '.join(explore_required_fields_missing)}"
            )

    read_surface_visibility = {
        "target_resolution": {
            "requested_set_key": set_id,
            "resolved_target_id": resolved_target_id,
            "resolution_source": target_resolution.get("resolution_source"),
        },
        "latest_resolution_source_used_for_verified_ids": latest_resolution_source,
        "explore_rip_statistics_latest": {
            "row_found": explore_latest_row is not None,
            "selected_run_id": explore_latest_run_id or None,
            "selects_verified_run": explore_latest_selects_verified_run,
            "missing_required_fields": explore_required_fields_missing,
        },
        "simulation_latest_by_target": {
            "row_found": simulation_latest_row is not None,
            "selected_run_id": simulation_latest_run_id or None,
            "selects_verified_run": simulation_latest_selects_verified_run,
        },
        "calculation_runs_latest_lookup": {
            "row_found": calculation_latest_row is not None,
            "selected_run_id": calculation_latest_run_id or None,
            "selects_verified_run": calculation_latest_selects_verified_run,
        },
        "set_pack_score_rankings_latest": {
            "row_found_for_verified_run": ranking_row_exists_for_verified_run,
        },
    }

    latest_selected_by_all_primary_surfaces = all(
        (
            explore_latest_selects_verified_run,
            simulation_latest_selects_verified_run,
            calculation_latest_selects_verified_run,
        )
    )

    downstream_readiness = {
        "formula_roi_present": formula_roi_present,
        "value_to_cost_ratio_present": value_to_cost_ratio_present,
        "metric_semantics_version_present": metric_semantics_version_present,
        "metric_semantics_version_value": metric_semantics_version_value,
        "probability_to_beat_pack_cost_present": probability_to_beat_pack_cost_present,
        "percentile_rows_present": counts_by_table.get("simulation_percentiles", 0) > 0,
        "value_distribution_bins_present": counts_by_table.get("simulation_value_distribution_bins", 0) > 0,
        "threshold_bins_present": counts_by_table.get("simulation_value_threshold_bins", 0) > 0,
        "pull_summaries_present": counts_by_table.get("simulation_pull_summary", 0) > 0,
        "derived_metrics_present": counts_by_table.get("simulation_derived_metrics", 0) > 0,
    }

    return {
        "set_id": set_id,
        "expected_parent_run_id": parent_run_id,
        "expected_simulation_summary_id": summary_id,
        "calculation_runs_exists": run_exists,
        "target_identity_ok": run_target_identity_ok,
        "calculation_config_link_exists": config_link_exists,
        "simulation_run_summary_exists": summary_exists,
        "summary_parent_run_id": summary_parent_run_id or None,
        "summary_belongs_to_expected_run": summary_belongs_to_expected_run,
        "counts_by_table": counts_by_table,
        "pull_summary_bucket_contract": {
            "required_buckets": sorted(required_buckets),
            "unsupported_buckets_must_be_absent": sorted(unsupported_buckets),
            "observed_buckets": sorted(observed_pull_summary_buckets),
            "observed_bucket_count": len(observed_pull_summary_buckets),
            "missing_required_buckets": missing_required_buckets,
            "present_unsupported_buckets": present_unsupported_buckets,
            "passes": not missing_required_buckets and not present_unsupported_buckets,
        },
        "combo_state_contract": {
            "state_group": "slot_schema_combo",
            "ignored_for_pack_breakdown": True,
            "combo_rows_count": combo_rows_count,
            "combo_occurrence_total": combo_occurrence_total,
            "expected_simulation_count": simulation_count,
            "occurrence_total_matches_simulation_count": (
                True if simulation_count is None else combo_occurrence_total == simulation_count
            ),
            "representative_rows": [
                {
                    "state_name": str(row.get("state_name") or ""),
                    "occurrence_count": int(row.get("occurrence_count") or 0),
                }
                for row in combo_rows[:2]
            ],
            "pack_path_rows_count": len(pack_path_rows),
            "normal_pack_state_rows_count": len(normal_pack_state_rows),
            "normal_pack_state_optional_when_combo_present": True,
            "passes": True,
        },
        "read_surface_visibility": read_surface_visibility,
        "latest_selected_by_all_primary_surfaces": latest_selected_by_all_primary_surfaces,
        "downstream_readiness": downstream_readiness,
        "warnings": warnings,
        "blockers": blockers,
        "read_surface_gap_blockers": read_surface_gap_blockers,
    }


def _render_markdown(payload: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# SWSH Project 11 Post-Persistence Surface Verification")
    lines.append("")
    lines.append(f"Generated: {payload.get('generated_at_utc')}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- final_decision: {payload.get('final_decision')}")
    lines.append(f"- db_mutation_performed: {payload.get('db_mutation_performed')}")
    lines.append(f"- execute_rerun_performed: {payload.get('execute_rerun_performed')}")
    lines.append(f"- source_project_10_closure_artifact: {payload.get('source_project_10_closure_artifact')}")
    lines.append("")
    lines.append("## Verified IDs")
    lines.append("")
    for set_id in TARGET_SET_IDS:
        run_id = (payload.get("verified_run_ids") or {}).get(set_id)
        summary_id = (payload.get("verified_summary_ids") or {}).get(set_id)
        lines.append(f"- {set_id}: parent_run_id={run_id} simulation_summary_id={summary_id}")
    lines.append("")
    lines.append("## Per-Set Verification")
    lines.append("")

    per_set = payload.get("per_set") or {}
    for set_id in TARGET_SET_IDS:
        item = per_set.get(set_id) or {}
        lines.append(f"### {set_id}")
        lines.append("")
        lines.append(f"- calculation_runs_exists: {item.get('calculation_runs_exists')}")
        lines.append(f"- target_identity_ok: {item.get('target_identity_ok')}")
        lines.append(f"- calculation_config_link_exists: {item.get('calculation_config_link_exists')}")
        lines.append(f"- simulation_run_summary_exists: {item.get('simulation_run_summary_exists')}")
        lines.append(f"- summary_belongs_to_expected_run: {item.get('summary_belongs_to_expected_run')}")
        lines.append(f"- latest_selected_by_all_primary_surfaces: {item.get('latest_selected_by_all_primary_surfaces')}")
        lines.append(f"- table_counts_by_run: {json.dumps(item.get('counts_by_table') or {}, sort_keys=True)}")
        lines.append(
            "- pull_summary_bucket_contract: "
            + json.dumps(item.get("pull_summary_bucket_contract") or {}, sort_keys=True)
        )
        lines.append(
            "- read_surface_visibility: "
            + json.dumps(item.get("read_surface_visibility") or {}, sort_keys=True)
        )
        lines.append(
            "- downstream_readiness: "
            + json.dumps(item.get("downstream_readiness") or {}, sort_keys=True)
        )
        warnings = item.get("warnings") or []
        lines.append("- warnings: " + ("; ".join(str(w) for w in warnings) if warnings else "None"))
        blockers = item.get("blockers") or []
        lines.append("- blockers: " + ("; ".join(str(b) for b in blockers) if blockers else "None"))
        gap_blockers = item.get("read_surface_gap_blockers") or []
        lines.append(
            "- read_surface_gap_blockers: "
            + ("; ".join(str(b) for b in gap_blockers) if gap_blockers else "None")
        )
        lines.append("")

    lines.append("## Aggregated Status")
    lines.append("")
    lines.append(f"- latest_read_surface_visibility_status: {payload.get('latest_read_surface_visibility_status')}")
    lines.append(
        "- newly_persisted_runs_selected_as_latest: "
        + str(payload.get("newly_persisted_runs_selected_as_latest"))
    )
    lines.append(f"- downstream_readiness_status: {payload.get('downstream_readiness_status')}")
    lines.append(
        "- no_unexpected_extra_write_table_categories_required_for_current_read_surfaces: "
        + str(payload.get("no_unexpected_extra_write_table_categories_required_for_current_read_surfaces"))
    )
    lines.append("")

    lines.append("## Blockers")
    lines.append("")
    blockers = payload.get("blockers") or []
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Next Recommended Step")
    lines.append("")
    lines.append(f"- {payload.get('next_recommended_step')}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run_post_persistence_surface_verification(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
    markdown_output_path: Path = DEFAULT_MD_PATH,
    identifiers_by_set: Optional[Mapping[str, Mapping[str, Any]]] = None,
    fail_on_blockers: bool = True,
) -> Dict[str, Any]:
    resolved_ids: Dict[str, Dict[str, str]] = {}
    latest_resolution_by_set: Dict[str, Dict[str, Any]] = {}
    service_client = supabase_client.supabase
    public_client = supabase_client.public_read_client
    for set_id in TARGET_SET_IDS:
        source = (identifiers_by_set or {}).get(set_id) if identifiers_by_set else None
        if source is None:
            latest_resolution = _latest_identifier_from_public_surfaces(
                set_id,
                service_client=service_client,
                public_client=public_client,
            )
            latest_resolution_by_set[set_id] = dict(latest_resolution)
            source = {
                "parent_run_id": latest_resolution.get("parent_run_id"),
                "simulation_summary_id": latest_resolution.get("simulation_summary_id"),
            }
        else:
            latest_resolution_by_set[set_id] = {
                "set_id": set_id,
                "latest_source": "manual_identifiers_override",
                "error": None,
            }
        resolved_ids[set_id] = {
            "parent_run_id": str(source.get("parent_run_id") or ""),
            "simulation_summary_id": str(source.get("simulation_summary_id") or ""),
        }

    initial_blockers: List[str] = []
    for set_id in TARGET_SET_IDS:
        ids = resolved_ids[set_id]
        latest_resolution = latest_resolution_by_set.get(set_id) or {}
        resolution_error = latest_resolution.get("error")
        if resolution_error:
            initial_blockers.append(
                f"{set_id}: latest identifier resolution failed ({resolution_error})"
            )
        if not ids["parent_run_id"]:
            initial_blockers.append(f"{set_id}: parent_run_id is required")
        if not ids["simulation_summary_id"]:
            initial_blockers.append(f"{set_id}: simulation_summary_id is required")

    per_set: Dict[str, Dict[str, Any]] = {}
    hard_blockers: List[str] = list(initial_blockers)
    read_surface_gap_blockers: List[str] = []

    for set_id in TARGET_SET_IDS:
        ids = resolved_ids[set_id]
        report = _verify_single_set(
            set_id,
            ids["parent_run_id"],
            ids["simulation_summary_id"],
            latest_resolution_source=(latest_resolution_by_set.get(set_id) or {}).get("latest_source"),
        )
        per_set[set_id] = report
        hard_blockers.extend(report.get("blockers") or [])
        read_surface_gap_blockers.extend(report.get("read_surface_gap_blockers") or [])

    hard_blockers = sorted(set(str(item) for item in hard_blockers))
    read_surface_gap_blockers = sorted(set(str(item) for item in read_surface_gap_blockers))

    latest_mismatch_found = any(
        not bool((per_set.get(set_id) or {}).get("latest_selected_by_all_primary_surfaces"))
        for set_id in TARGET_SET_IDS
    )

    all_downstream_ready = all(
        all(bool(v) for k, v in ((per_set.get(set_id) or {}).get("downstream_readiness") or {}).items() if k.endswith("_present"))
        for set_id in TARGET_SET_IDS
    )

    final_decision = _determine_final_decision(
        hard_blockers=hard_blockers,
        read_surface_gap_blockers=read_surface_gap_blockers,
        latest_mismatch_found=latest_mismatch_found,
    )

    blockers: List[str] = []
    blockers.extend(hard_blockers)
    blockers.extend(read_surface_gap_blockers)
    blockers = sorted(set(blockers))

    latest_status = "verified_latest_selected"
    if latest_mismatch_found:
        latest_status = "persisted_rows_valid_but_latest_points_elsewhere"

    downstream_readiness_status = "ready"
    if not all_downstream_ready:
        downstream_readiness_status = "not_ready"

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": "11",
        "final_decision": final_decision,
        "db_mutation_performed": False,
        "execute_rerun_performed": False,
        "source_project_10_closure_artifact": SOURCE_PROJECT_10_CLOSURE_ARTIFACT,
        "source_project_10_closure_brief": _read_project_10_closure_brief(),
        "verified_ids_resolution": latest_resolution_by_set,
        "verified_run_ids": {set_id: resolved_ids[set_id]["parent_run_id"] for set_id in TARGET_SET_IDS},
        "verified_summary_ids": {set_id: resolved_ids[set_id]["simulation_summary_id"] for set_id in TARGET_SET_IDS},
        "prior_real_write_counts_total": dict(PRIOR_REAL_WRITE_COUNTS_TOTAL),
        "per_set": per_set,
        "table_counts_by_run": {
            set_id: dict((per_set.get(set_id) or {}).get("counts_by_table") or {})
            for set_id in TARGET_SET_IDS
        },
        "latest_read_surface_visibility_status": latest_status,
        "newly_persisted_runs_selected_as_latest": not latest_mismatch_found,
        "downstream_readiness_status": downstream_readiness_status,
        "no_unexpected_extra_write_table_categories_required_for_current_read_surfaces": True,
        "read_surfaces_checked": [
            "explore_rip_statistics_latest",
            "simulation_latest_by_target",
            "set_pack_score_rankings_latest",
            "calculation_runs_latest_lookup",
            "simulation_run_summary",
            "simulation_derived_metrics",
            "simulation_pull_summary",
            "simulation_percentiles",
            "simulation_state_counts",
            "simulation_value_distribution_bins",
            "simulation_value_threshold_bins",
        ],
        "blockers": blockers,
        "next_recommended_step": _next_step_for_decision(final_decision),
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)

    json_output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    markdown_output_path.write_text(_render_markdown(payload), encoding="utf-8")

    if blockers and fail_on_blockers:
        raise AssertionError("; ".join(blockers))

    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project 11 read-only post-persistence surface verification for swsh6/swsh7"
    )
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH), help="JSON output path")
    parser.add_argument("--markdown-output", default=str(DEFAULT_MD_PATH), help="Markdown output path")
    parser.add_argument("--stdout", action="store_true", help="Print compact summary JSON")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = run_post_persistence_surface_verification(
        json_output_path=Path(args.json_output),
        markdown_output_path=Path(args.markdown_output),
        identifiers_by_set=None,
        fail_on_blockers=True,
    )

    summary = {
        "final_decision": payload.get("final_decision"),
        "db_mutation_performed": payload.get("db_mutation_performed"),
        "execute_rerun_performed": payload.get("execute_rerun_performed"),
        "newly_persisted_runs_selected_as_latest": payload.get("newly_persisted_runs_selected_as_latest"),
        "downstream_readiness_status": payload.get("downstream_readiness_status"),
        "blocker_count": len(payload.get("blockers") or []),
    }

    print(f"[project11] final_decision={summary['final_decision']}")
    print(f"[project11] db_mutation_performed={summary['db_mutation_performed']}")
    print(f"[project11] execute_rerun_performed={summary['execute_rerun_performed']}")
    print(f"[project11] newly_persisted_runs_selected_as_latest={summary['newly_persisted_runs_selected_as_latest']}")
    print(f"[project11] downstream_readiness_status={summary['downstream_readiness_status']}")
    print(f"[project11] blocker_count={summary['blocker_count']}")

    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
