"""Project 12 read-only backend/API surface smoke verification for swsh6/swsh7.

This script validates production-facing read paths for persisted swsh6/swsh7 runs
without mutating database state or re-running execute.

Hard guardrails:
- No execute rerun
- No DB mutation
- Read-only SELECT/service calls only
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from backend.db.clients import supabase_client
from backend.db.services.calculation_run_query_service import get_latest_evr_run_snapshot
from backend.db.services.explore_page_service import ExplorePageError, get_explore_page_payload
from backend.db.services.explore_rip_statistics_service import (
    ExploreRipStatisticsTargetsError,
    get_rip_statistics_targets_payload,
)


DEFAULT_JSON_PATH = Path("logs/audits/swsh_project_12_backend_surface_smoke.json")
DEFAULT_MD_PATH = Path("backend/docs/audits/SWSH_PROJECT_12_BACKEND_SURFACE_SMOKE.md")

TARGET_SET_IDS = ("swsh6", "swsh7")

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

CRITICAL_FIELDS = (
    "pack_cost",
    "mean_value",
    "median_value",
    "roi",
    "roi_percent",
    "prob_profit",
)

RIP_REQUIRED_FIELDS = (
    "pack_score",
    "pack_cost",
    "mean_value",
    "median_value",
    "roi_percent",
    "prob_profit",
)

RATIO_FIELDS = (
    "mean_value_to_cost_ratio",
    "p95_value_to_cost_ratio",
)

REQUIRED_READ_PATH_TABLES = (
    "explore_rip_statistics_latest",
    "simulation_latest_by_target",
    "set_pack_score_rankings_latest",
    "simulation_run_summary",
    "simulation_derived_metrics",
    "simulation_value_distribution_bins",
    "simulation_value_threshold_bins",
    "simulation_percentiles",
    "simulation_pull_summary",
)

READ_PATH_INVENTORY: Dict[str, Dict[str, Any]] = {
    "api_routes": {
        "explore_or_set_detail": "/explore/page",
        "rip_targets_simple_or_expert": "/explore/rip-statistics/targets",
        "latest_summary_snapshot": "/evr/runs/latest",
    },
    "service_functions": {
        "explore_page": "backend.db.services.explore_page_service.get_explore_page_payload",
        "rip_targets": "backend.db.services.explore_rip_statistics_service.get_rip_statistics_targets_payload",
        "latest_snapshot": "backend.db.services.calculation_run_query_service.get_latest_evr_run_snapshot",
    },
    "table_readers": {
        "explore_rip_statistics_latest": [
            "get_explore_page_payload",
            "get_rip_statistics_targets_payload",
        ],
        "simulation_latest_by_target": ["get_explore_page_payload"],
        "set_pack_score_rankings_latest": [
            "get_explore_page_payload",
            "get_rip_statistics_targets_payload",
        ],
        "simulation_run_summary": [
            "get_explore_page_payload",
            "get_latest_evr_run_snapshot",
        ],
        "simulation_derived_metrics": [
            "get_explore_page_payload",
            "get_latest_evr_run_snapshot",
        ],
        "simulation_value_distribution_bins": ["get_explore_page_payload"],
        "simulation_value_threshold_bins": ["get_explore_page_payload"],
        "simulation_percentiles": [
            "get_explore_page_payload",
            "get_latest_evr_run_snapshot",
        ],
        "simulation_pull_summary": ["get_explore_page_payload"],
    },
}


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


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _is_json_serializable(value: Any) -> bool:
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_to_jsonable(item) for item in value)
    return str(value)


def _validate_roi_semantics(summary: Mapping[str, Any], tolerance: float = 1e-6) -> Dict[str, Any]:
    pack_cost = summary.get("pack_cost")
    mean_value = summary.get("mean_value")
    roi = summary.get("roi")
    roi_percent = summary.get("roi_percent")

    try:
        pack_cost_f = float(pack_cost)
        mean_value_f = float(mean_value)
        roi_f = float(roi)
        roi_percent_f = float(roi_percent)
    except (TypeError, ValueError):
        return {
            "checked": False,
            "passes": False,
            "reason": "roi inputs missing or non-numeric",
        }

    if pack_cost_f <= 0:
        return {
            "checked": False,
            "passes": False,
            "reason": "pack_cost must be positive",
        }

    expected_roi = (mean_value_f - pack_cost_f) / pack_cost_f
    expected_roi_percent = expected_roi * 100.0
    roi_delta = abs(expected_roi - roi_f)
    roi_percent_delta = abs(expected_roi_percent - roi_percent_f)

    return {
        "checked": True,
        "passes": roi_delta <= tolerance and roi_percent_delta <= tolerance,
        "expected_roi": expected_roi,
        "reported_roi": roi_f,
        "roi_delta": roi_delta,
        "expected_roi_percent": expected_roi_percent,
        "reported_roi_percent": roi_percent_f,
        "roi_percent_delta": roi_percent_delta,
        "tolerance": tolerance,
    }


def _verify_single_set(
    *,
    set_id: str,
    expected_parent_run_id: str,
    expected_summary_id: str,
    targets_payload: Mapping[str, Any],
) -> Dict[str, Any]:
    public_client = supabase_client.public_read_client
    service_client = supabase_client.supabase

    blockers: List[str] = []
    read_path_gap_blockers: List[str] = []
    warnings: List[str] = []

    resolved_target_id = set_id
    target_resolution_source = "requested_set_key"
    for key in ("canonical_key", "pokemon_api_set_id", "id"):
        rows = _fetch_rows(
            "sets",
            filters={key: set_id},
            limit=1,
            client=service_client,
        )
        if rows and _is_non_empty(rows[0].get("id")):
            resolved_target_id = str(rows[0].get("id"))
            target_resolution_source = key
            break

    explore_rows = _fetch_rows(
        "explore_rip_statistics_latest",
        filters={"set_id": resolved_target_id},
        limit=1,
        client=public_client,
    )
    explore_latest_row = explore_rows[0] if explore_rows else None

    if not explore_latest_row:
        blockers.append(f"{set_id}: latest explore_rip_statistics_latest row missing")

    simulation_latest_rows = _fetch_rows(
        "simulation_latest_by_target",
        filters={"target_type": "set", "target_id": resolved_target_id},
        order_by="run_at",
        desc=True,
        limit=1,
        client=public_client,
    )
    simulation_latest_row = simulation_latest_rows[0] if simulation_latest_rows else None
    if not simulation_latest_row:
        read_path_gap_blockers.append(f"{set_id}: simulation_latest_by_target has no latest row")

    ranking_rows = _fetch_rows(
        "set_pack_score_rankings_latest",
        filters={"target_id": resolved_target_id, "calculation_run_id": expected_parent_run_id},
        limit=1,
        client=public_client,
    )
    ranking_row = ranking_rows[0] if ranking_rows else None
    if not ranking_row:
        read_path_gap_blockers.append(
            f"{set_id}: set_pack_score_rankings_latest missing row for verified run_id={expected_parent_run_id}"
        )

    explore_latest_run_id = str((explore_latest_row or {}).get("calculation_run_id") or "")
    simulation_latest_run_id = str((simulation_latest_row or {}).get("calculation_run_id") or "")

    explore_latest_matches = bool(explore_latest_run_id == expected_parent_run_id)
    simulation_latest_matches = bool(simulation_latest_run_id == expected_parent_run_id)

    if not explore_latest_matches:
        blockers.append(
            f"{set_id}: latest run id mismatch on explore_rip_statistics_latest "
            f"(expected={expected_parent_run_id} actual={explore_latest_run_id or None})"
        )
    if not simulation_latest_matches:
        blockers.append(
            f"{set_id}: latest run id mismatch on simulation_latest_by_target "
            f"(expected={expected_parent_run_id} actual={simulation_latest_run_id or None})"
        )

    latest_snapshot_error: Optional[str] = None
    latest_snapshot: Optional[Dict[str, Any]] = None
    latest_snapshot_lookup_ids = [resolved_target_id]
    if set_id != resolved_target_id:
        latest_snapshot_lookup_ids.append(set_id)
    for candidate_target_id in latest_snapshot_lookup_ids:
        try:
            latest_snapshot = get_latest_evr_run_snapshot(target_type="set", target_id=candidate_target_id)
            if latest_snapshot:
                break
        except Exception as exc:
            latest_snapshot_error = f"{type(exc).__name__}: {exc}"

    latest_snapshot_run_id = str((latest_snapshot or {}).get("calculation_run_id") or "")
    latest_snapshot_matches = bool(latest_snapshot_run_id == expected_parent_run_id)
    if latest_snapshot is None:
        read_path_gap_blockers.append(f"{set_id}: latest snapshot service returned no payload")
    elif not latest_snapshot_matches:
        read_path_gap_blockers.append(
            f"{set_id}: latest run id mismatch on latest snapshot service "
            f"(expected={expected_parent_run_id} actual={latest_snapshot_run_id or None})"
        )

    missing_or_null_rip_fields: List[str] = []
    for field in RIP_REQUIRED_FIELDS:
        if not _is_non_empty((explore_latest_row or {}).get(field)):
            missing_or_null_rip_fields.append(field)
    if missing_or_null_rip_fields:
        blockers.append(
            f"{set_id}: explore RIP fields are null/missing: {', '.join(sorted(missing_or_null_rip_fields))}"
        )


    explore_payload_error: Optional[str] = None
    explore_payload: Optional[Dict[str, Any]] = None
    try:
        explore_payload = get_explore_page_payload(
            target_type="set",
            target_id=resolved_target_id,
            limit_distribution_bins=50,
            limit_top_hits=10,
        )
    except ExplorePageError as exc:
        explore_payload_error = f"{exc.code}: {exc.message}"
        blockers.append(f"{set_id}: explore page service failed: {explore_payload_error}")
    except Exception as exc:
        explore_payload_error = f"{type(exc).__name__}: {exc}"
        blockers.append(f"{set_id}: explore page service crashed: {explore_payload_error}")

    explore_payload_meta_sources = dict(((explore_payload or {}).get("meta") or {}).get("sources") or {})

    summary = dict((latest_snapshot or {}).get("summary") or {})
    summary_source = "latest_snapshot"
    if not summary:
        summary = dict((explore_payload or {}).get("summary") or {})
        summary_source = "explore_payload"

    missing_or_null_critical_fields: List[str] = []
    for field in CRITICAL_FIELDS:
        if not _is_non_empty(summary.get(field)):
            missing_or_null_critical_fields.append(field)
    if missing_or_null_critical_fields:
        blockers.append(
            f"{set_id}: critical fields are null/missing: {', '.join(sorted(missing_or_null_critical_fields))}"
        )

    ratio_fields_present = {
        field: _is_non_empty((explore_latest_row or {}).get(field)) or _is_non_empty(summary.get(field))
        for field in RATIO_FIELDS
    }
    if not all(ratio_fields_present.values()):
        missing = [k for k, present in ratio_fields_present.items() if not present]
        warnings.append(f"{set_id}: value-to-cost ratio fields missing on exposed backend payload: {', '.join(missing)}")

    roi_semantics = _validate_roi_semantics(summary)
    if not bool(roi_semantics.get("passes")):
        blockers.append(
            f"{set_id}: formula ROI semantics check failed ({roi_semantics.get('reason') or 'delta beyond tolerance'})"
        )

    monte_carlo_v2_marker_found = False
    for marker_key in ("derived_metric_version", "score_version", "normalization_mode"):
        marker_value = str(summary.get(marker_key) or "").strip().lower()
        if "monte" in marker_value and "v2" in marker_value:
            monte_carlo_v2_marker_found = True
            break
    if monte_carlo_v2_marker_found:
        read_path_gap_blockers.append(
            f"{set_id}: latest summary markers indicate monte carlo v2-only assumption"
        )

    required_source_keys = {
        "simulation_pull_summary": "pull summary",
        "simulation_percentiles": "percentiles",
        "simulation_value_distribution_bins": "distribution bins",
        "simulation_value_threshold_bins": "threshold bins",
    }
    source_status: Dict[str, Dict[str, Any]] = {}
    for key, label in required_source_keys.items():
        status = str(explore_payload_meta_sources.get(key) or "NOT_REPORTED")
        ok = status in {"OK", "SKIPPED_CANONICAL", "SKIPPED_RIP_SUMMARY"}
        source_status[key] = {"status": status, "ok": ok, "label": label}
        if not ok:
            read_path_gap_blockers.append(f"{set_id}: explore page source status for {key} is {status}")

    distribution_count = len((explore_payload or {}).get("distribution_bins") or [])
    threshold_count = len((explore_payload or {}).get("threshold_bins") or [])
    percentile_count = len((explore_payload or {}).get("percentiles") or [])
    pull_summary_count = len((explore_payload or {}).get("rankings") or [])

    if distribution_count <= 0:
        read_path_gap_blockers.append(f"{set_id}: distribution bins payload is empty")
    if threshold_count <= 0:
        read_path_gap_blockers.append(f"{set_id}: threshold bins payload is empty")
    if percentile_count <= 0:
        read_path_gap_blockers.append(f"{set_id}: percentiles payload is empty")
    if pull_summary_count <= 0:
        read_path_gap_blockers.append(f"{set_id}: pull summary payload is empty")

    set_targets = list((targets_payload or {}).get("targets") or [])
    target_row = next(
        (
            row
            for row in set_targets
            if str(row.get("target_id") or "") in {set_id, resolved_target_id}
        ),
        None,
    )
    if target_row is None:
        read_path_gap_blockers.append(f"{set_id}: rip targets endpoint payload does not include set")

    serializability = {
        "explore_latest_row": _is_json_serializable(explore_latest_row),
        "simulation_latest_row": _is_json_serializable(simulation_latest_row),
        "latest_snapshot": _is_json_serializable(latest_snapshot),
        "explore_payload": _is_json_serializable(explore_payload),
        "rip_target_row": _is_json_serializable(target_row),
    }
    if not all(serializability.values()):
        failing = [k for k, ok in serializability.items() if not ok]
        blockers.append(f"{set_id}: payload not JSON serializable: {', '.join(sorted(failing))}")

    slot_schema_compatibility_status = "compatible"
    if read_path_gap_blockers:
        slot_schema_compatibility_status = "read_path_gap_detected"
    if blockers:
        slot_schema_compatibility_status = "blocking_failure"

    return {
        "set_id": set_id,
        "expected_parent_run_id": expected_parent_run_id,
        "expected_simulation_summary_id": expected_summary_id,
        "target_resolution": {
            "requested_set_key": set_id,
            "resolved_target_id": resolved_target_id,
            "resolution_source": target_resolution_source,
        },
        "latest_run_id_checks": {
            "explore_rip_statistics_latest": {
                "selected_run_id": explore_latest_run_id or None,
                "matches_expected": explore_latest_matches,
            },
            "simulation_latest_by_target": {
                "selected_run_id": simulation_latest_run_id or None,
                "matches_expected": simulation_latest_matches,
            },
            "latest_snapshot_service": {
                "selected_run_id": latest_snapshot_run_id or None,
                "matches_expected": latest_snapshot_matches,
                "service_error": latest_snapshot_error,
            },
        },
        "critical_field_status": {
            "summary_source": summary_source,
            "missing_or_null_critical_fields": missing_or_null_critical_fields,
            "missing_or_null_rip_fields": missing_or_null_rip_fields,
        },
        "roi_semantics": roi_semantics,
        "ratio_field_presence": ratio_fields_present,
        "payload_counts": {
            "distribution_bins": distribution_count,
            "threshold_bins": threshold_count,
            "percentiles": percentile_count,
            "pull_summary": pull_summary_count,
        },
        "explore_page_source_status": source_status,
        "serialization_status": serializability,
        "slot_schema_compatibility_status": slot_schema_compatibility_status,
        "warnings": warnings,
        "blockers": sorted(set(blockers)),
        "read_path_gap_blockers": sorted(set(read_path_gap_blockers)),
        "service_payloads": {
            "explore_latest_row": explore_latest_row,
            "simulation_latest_row": simulation_latest_row,
            "ranking_row_for_expected_run": ranking_row,
            "latest_snapshot": latest_snapshot,
            "explore_payload_error": explore_payload_error,
            "explore_meta_sources": explore_payload_meta_sources,
        },
    }


def _determine_final_decision(
    *,
    blockers: List[str],
    read_path_gap_blockers: List[str],
    warnings: List[str],
) -> str:
    if blockers:
        return "not_closed_blockers_remaining"
    if read_path_gap_blockers:
        return "closed_backend_surface_smoke_blocked_on_read_path_gap"
    if warnings:
        return "closed_backend_surface_smoke_valid_with_non_blocking_warnings"
    return "closed_backend_surface_smoke_verified"


def _next_step_for_decision(final_decision: str) -> str:
    if final_decision == "closed_backend_surface_smoke_verified":
        return "Proceed to controlled frontend smoke and reporting publication checks using the same persisted run IDs."
    if final_decision == "closed_backend_surface_smoke_valid_with_non_blocking_warnings":
        return "Track warning-only fields in a follow-up read-path hardening pass without any DB mutations."
    if final_decision == "closed_backend_surface_smoke_blocked_on_read_path_gap":
        return "Open a backend read-path patch plan for missing/failed service exposures while keeping swsh6/swsh7 data immutable."
    return "Resolve blockers with targeted backend read-only diagnostics before any next rollout phase."


def _render_markdown(payload: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# SWSH Project 12 Backend Surface Smoke")
    lines.append("")
    lines.append(f"Generated: {payload.get('generated_at_utc')}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- final_decision: {payload.get('final_decision')}")
    lines.append(f"- db_mutation_performed: {payload.get('db_mutation_performed')}")
    lines.append(f"- execute_rerun_performed: {payload.get('execute_rerun_performed')}")
    lines.append("")
    lines.append("## Verified Run IDs")
    lines.append("")
    for set_id in TARGET_SET_IDS:
        row = (payload.get("verified_run_ids") or {}).get(set_id) or {}
        lines.append(
            f"- {set_id}: parent_run_id={row.get('parent_run_id')} simulation_summary_id={row.get('simulation_summary_id')}"
        )
    lines.append("")
    lines.append("## Backend Surfaces Checked")
    lines.append("")
    for item in payload.get("backend_surfaces_checked") or []:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Table Read Coverage")
    lines.append("")
    lines.append("- " + json.dumps(payload.get("table_read_coverage") or {}, sort_keys=True))
    lines.append("")
    lines.append("## Per-Set Status")
    lines.append("")
    per_set = payload.get("per_set") or {}
    for set_id in TARGET_SET_IDS:
        row = per_set.get(set_id) or {}
        lines.append(f"### {set_id}")
        lines.append("")
        lines.append("- latest_run_id_checks: " + json.dumps(row.get("latest_run_id_checks") or {}, sort_keys=True))
        lines.append("- critical_field_status: " + json.dumps(row.get("critical_field_status") or {}, sort_keys=True))
        lines.append("- payload_counts: " + json.dumps(row.get("payload_counts") or {}, sort_keys=True))
        lines.append("- serialization_status: " + json.dumps(row.get("serialization_status") or {}, sort_keys=True))
        lines.append(f"- slot_schema_compatibility_status: {row.get('slot_schema_compatibility_status')}")
        lines.append("- warnings: " + ("; ".join(row.get("warnings") or []) if row.get("warnings") else "None"))
        lines.append("- blockers: " + ("; ".join(row.get("blockers") or []) if row.get("blockers") else "None"))
        lines.append(
            "- read_path_gap_blockers: "
            + ("; ".join(row.get("read_path_gap_blockers") or []) if row.get("read_path_gap_blockers") else "None")
        )
        lines.append("")

    lines.append("## Serialization Status")
    lines.append("")
    lines.append(f"- payloads_json_serializable: {payload.get('payloads_json_serializable')}")
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


def run_backend_surface_smoke(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
    markdown_output_path: Path = DEFAULT_MD_PATH,
    identifiers_by_set: Optional[Mapping[str, Mapping[str, Any]]] = None,
    fail_on_blockers: bool = True,
) -> Dict[str, Any]:
    resolved_ids: Dict[str, Dict[str, str]] = {}
    for set_id in TARGET_SET_IDS:
        source = (identifiers_by_set or PROJECT_10_3_IDENTIFIERS).get(set_id) or {}
        resolved_ids[set_id] = {
            "parent_run_id": str(source.get("parent_run_id") or ""),
            "simulation_summary_id": str(source.get("simulation_summary_id") or ""),
        }

    blockers: List[str] = []
    for set_id in TARGET_SET_IDS:
        if not resolved_ids[set_id]["parent_run_id"]:
            blockers.append(f"{set_id}: parent_run_id is required")
        if not resolved_ids[set_id]["simulation_summary_id"]:
            blockers.append(f"{set_id}: simulation_summary_id is required")

    targets_payload: Dict[str, Any] = {}
    targets_error: Optional[str] = None
    try:
        targets_payload = get_rip_statistics_targets_payload(limit=200)
    except ExploreRipStatisticsTargetsError as exc:
        targets_error = f"{exc.code}: {exc.message}"
        blockers.append(f"rip statistics targets service failed: {targets_error}")
    except Exception as exc:
        targets_error = f"{type(exc).__name__}: {exc}"
        blockers.append(f"rip statistics targets service crashed: {targets_error}")

    per_set: Dict[str, Dict[str, Any]] = {}
    warning_items: List[str] = []
    read_path_gap_blockers: List[str] = []

    if not blockers:
        for set_id in TARGET_SET_IDS:
            set_payload = _verify_single_set(
                set_id=set_id,
                expected_parent_run_id=resolved_ids[set_id]["parent_run_id"],
                expected_summary_id=resolved_ids[set_id]["simulation_summary_id"],
                targets_payload=targets_payload,
            )
            per_set[set_id] = set_payload
            blockers.extend(set_payload.get("blockers") or [])
            read_path_gap_blockers.extend(set_payload.get("read_path_gap_blockers") or [])
            warning_items.extend(set_payload.get("warnings") or [])

    blockers = sorted(set(str(item) for item in blockers))
    read_path_gap_blockers = sorted(set(str(item) for item in read_path_gap_blockers))
    warning_items = sorted(set(str(item) for item in warning_items))

    table_read_coverage: Dict[str, bool] = {}
    for table_name in REQUIRED_READ_PATH_TABLES:
        table_read_coverage[table_name] = False

    for set_id in TARGET_SET_IDS:
        row = per_set.get(set_id) or {}
        status = row.get("explore_page_source_status") or {}
        if row.get("service_payloads", {}).get("explore_latest_row"):
            table_read_coverage["explore_rip_statistics_latest"] = True
        if row.get("service_payloads", {}).get("simulation_latest_row"):
            table_read_coverage["simulation_latest_by_target"] = True
        if row.get("service_payloads", {}).get("ranking_row_for_expected_run"):
            table_read_coverage["set_pack_score_rankings_latest"] = True

        latest_snapshot = row.get("service_payloads", {}).get("latest_snapshot") or {}
        summary = latest_snapshot.get("summary") or {}
        if summary:
            table_read_coverage["simulation_run_summary"] = True
            table_read_coverage["simulation_derived_metrics"] = True

        if (row.get("payload_counts") or {}).get("distribution_bins", 0) > 0:
            table_read_coverage["simulation_value_distribution_bins"] = True
        if (row.get("payload_counts") or {}).get("threshold_bins", 0) > 0:
            table_read_coverage["simulation_value_threshold_bins"] = True
        if (row.get("payload_counts") or {}).get("percentiles", 0) > 0:
            table_read_coverage["simulation_percentiles"] = True
        if (row.get("payload_counts") or {}).get("pull_summary", 0) > 0:
            table_read_coverage["simulation_pull_summary"] = True

        if status.get("simulation_percentiles", {}).get("ok"):
            table_read_coverage["simulation_percentiles"] = True
        if status.get("simulation_pull_summary", {}).get("ok"):
            table_read_coverage["simulation_pull_summary"] = True
        if status.get("simulation_value_distribution_bins", {}).get("ok"):
            table_read_coverage["simulation_value_distribution_bins"] = True
        if status.get("simulation_value_threshold_bins", {}).get("ok"):
            table_read_coverage["simulation_value_threshold_bins"] = True

    payloads_json_serializable = _is_json_serializable(
        {
            "targets_payload": targets_payload,
            "per_set": per_set,
        }
    )
    if not payloads_json_serializable:
        blockers.append("top-level smoke payload is not JSON serializable")

    blockers = sorted(set(blockers))

    final_decision = _determine_final_decision(
        blockers=blockers,
        read_path_gap_blockers=read_path_gap_blockers,
        warnings=warning_items,
    )

    payload: Dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": "12",
        "final_decision": final_decision,
        "db_mutation_performed": False,
        "execute_rerun_performed": False,
        "verified_run_ids": dict(resolved_ids),
        "backend_surfaces_checked": [
            "/explore/page -> get_explore_page_payload",
            "/explore/rip-statistics/targets -> get_rip_statistics_targets_payload",
            "/evr/runs/latest -> get_latest_evr_run_snapshot",
            "latest views: explore_rip_statistics_latest, simulation_latest_by_target, set_pack_score_rankings_latest",
        ],
        "read_path_inventory": dict(READ_PATH_INVENTORY),
        "table_read_coverage": table_read_coverage,
        "targets_service_error": targets_error,
        "per_set": per_set,
        "payloads_json_serializable": payloads_json_serializable,
        "slot_schema_compatibility_status": (
            "compatible" if not read_path_gap_blockers and not blockers else "issues_detected"
        ),
        "warnings": warning_items,
        "read_path_gap_blockers": read_path_gap_blockers,
        "blockers": blockers,
        "next_recommended_step": _next_step_for_decision(final_decision),
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)

    payload_jsonable = _to_jsonable(payload)
    json_output_path.write_text(json.dumps(payload_jsonable, indent=2, sort_keys=True), encoding="utf-8")
    markdown_output_path.write_text(_render_markdown(payload_jsonable), encoding="utf-8")

    if blockers and fail_on_blockers:
        raise AssertionError("; ".join(blockers))

    return payload_jsonable


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project 12 read-only backend/API surface smoke verification for swsh6/swsh7"
    )
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH), help="JSON output path")
    parser.add_argument("--markdown-output", default=str(DEFAULT_MD_PATH), help="Markdown output path")
    parser.add_argument("--stdout", action="store_true", help="Print compact summary JSON")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    payload = run_backend_surface_smoke(
        json_output_path=Path(args.json_output),
        markdown_output_path=Path(args.markdown_output),
        identifiers_by_set=PROJECT_10_3_IDENTIFIERS,
        fail_on_blockers=False,
    )

    summary = {
        "final_decision": payload.get("final_decision"),
        "db_mutation_performed": payload.get("db_mutation_performed"),
        "execute_rerun_performed": payload.get("execute_rerun_performed"),
        "blocker_count": len(payload.get("blockers") or []),
        "read_path_gap_blocker_count": len(payload.get("read_path_gap_blockers") or []),
    }

    print(f"[project12] final_decision={summary['final_decision']}")
    print(f"[project12] db_mutation_performed={summary['db_mutation_performed']}")
    print(f"[project12] execute_rerun_performed={summary['execute_rerun_performed']}")
    print(f"[project12] blocker_count={summary['blocker_count']}")
    print(f"[project12] read_path_gap_blocker_count={summary['read_path_gap_blocker_count']}")

    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
