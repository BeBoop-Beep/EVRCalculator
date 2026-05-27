"""Project 17C.2 regular SWSH Lane 1 controlled persistence preflight (read-only).

Targets are fixed to:
- swsh5 (Battle Styles)
- swsh9 (Brilliant Stars)
- swsh10 (Astral Radiance)
- swsh11 (Lost Origin)
- swsh12 (Silver Tempest)

This preflight performs read-only checks only:
- verifies target identity resolution and expected local UUIDs
- checks latest-row presence in calculation and simulation views
- checks whether Explore payload resolution works when data exists

No writes are performed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.constants.tcg.pokemon.swordAndShieldEra.setMap import SET_ALIAS_MAP
from backend.db.clients.supabase_client import public_read_client
from backend.db.services.explore_page_service import ExplorePageError, get_explore_page_payload


DEFAULT_JSON_PATH = Path("logs/audits/swsh_lane1_controlled_persistence_preflight.json")

TARGET_ALLOWLIST = ("swsh5", "swsh9", "swsh10", "swsh11", "swsh12")

# Local identity snapshot from backend/constants/tcg/pokemon/pokemon_era_set_sync_report.json
EXPECTED_TARGET_UUID_BY_SET_ID = {
    "swsh5": "46ab39a7-dd96-4a2d-af0f-44b868918114",
    "swsh9": "a72c75bd-0d61-4643-b603-fef78425dcfa",
    "swsh10": "0d90b4ed-16a1-456c-81c6-83d2869d3846",
    "swsh11": "5109f22e-0799-46b5-a4ad-8861d1cfefee",
    "swsh12": "2d6ec108-70b2-4698-a21a-1af39828004f",
}


def _first_row(result: Any) -> Optional[Dict[str, Any]]:
    if result and result.data and len(result.data) > 0:
        return dict(result.data[0])
    return None


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _query_one(table: str, *, filters: Dict[str, Any], order_desc_column: Optional[str] = None) -> Dict[str, Any]:
    query = public_read_client.table(table).select("*")
    for column, value in filters.items():
        query = query.eq(column, value)
    if order_desc_column:
        query = query.order(order_desc_column, desc=True)
    result = query.limit(1).execute()
    return {
        "row_found": _first_row(result) is not None,
        "row": _first_row(result),
    }


def _resolve_target_set_row(set_id: str, expected_uuid: str) -> Dict[str, Any]:
    set_row_result = (
        public_read_client.table("sets")
        .select("id,name,canonical_key,pokemon_api_set_id")
        .eq("pokemon_api_set_id", set_id)
        .limit(1)
        .execute()
    )
    row = _first_row(set_row_result)

    canonical_key = SET_ALIAS_MAP.get(set_id)
    return {
        "set_id": set_id,
        "canonical_key": canonical_key,
        "expected_target_id": expected_uuid,
        "resolved": row is not None,
        "resolved_target_id": row.get("id") if row else None,
        "resolved_set_name": row.get("name") if row else None,
        "resolved_canonical_key": row.get("canonical_key") if row else None,
        "resolved_pokemon_api_set_id": row.get("pokemon_api_set_id") if row else None,
        "matches_expected_target_id": bool(row and str(row.get("id")) == expected_uuid),
        "matches_set_id": bool(row and _normalize_key(row.get("pokemon_api_set_id")) == _normalize_key(set_id)),
    }


def _probe_explore_payload(target_id: str) -> Dict[str, Any]:
    try:
        payload = get_explore_page_payload("set", target_id)
        summary = payload.get("summary") or {}
        meta = payload.get("meta") or {}
        return {
            "resolved": True,
            "error_code": None,
            "error_message": None,
            "summary_present": bool(summary),
            "meta_present": bool(meta),
            "run_id": summary.get("calculation_run_id") if isinstance(summary, dict) else None,
        }
    except ExplorePageError as exc:
        return {
            "resolved": False,
            "error_code": exc.code,
            "error_message": exc.message,
            "summary_present": False,
            "meta_present": False,
            "run_id": None,
        }
    except Exception as exc:
        return {
            "resolved": False,
            "error_code": type(exc).__name__,
            "error_message": str(exc),
            "summary_present": False,
            "meta_present": False,
            "run_id": None,
        }


def run_swsh_lane1_controlled_persistence_preflight(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
) -> Dict[str, Any]:
    started_at = time.perf_counter()

    per_set: Dict[str, Dict[str, Any]] = {}
    failures: list[str] = []

    for set_id in TARGET_ALLOWLIST:
        expected_uuid = EXPECTED_TARGET_UUID_BY_SET_ID[set_id]
        target_resolution = _resolve_target_set_row(set_id, expected_uuid)

        if not target_resolution["resolved"]:
            failures.append(f"{set_id}: target identity not resolved in sets table")
            per_set[set_id] = {
                "target_resolution": target_resolution,
                "execute_readiness": {
                    "ready": False,
                    "reasons": ["target_identity_missing"],
                },
            }
            continue

        resolved_target_id = str(target_resolution["resolved_target_id"])

        simulation_latest = _query_one(
            "simulation_latest_by_target",
            filters={
                "target_type": "set",
                "target_id": resolved_target_id,
            },
            order_desc_column="run_at",
        )

        calculation_runs = _query_one(
            "calculation_runs",
            filters={
                "target_type": "set",
                "target_id": resolved_target_id,
            },
            order_desc_column="created_at",
        )

        rip_latest = _query_one(
            "explore_rip_statistics_latest",
            filters={"set_id": resolved_target_id},
            order_desc_column="run_at",
        )

        has_any_persisted = bool(
            simulation_latest["row_found"]
            or calculation_runs["row_found"]
            or rip_latest["row_found"]
        )

        explore_probe = _probe_explore_payload(resolved_target_id)

        readiness_reasons = []
        if not target_resolution["matches_expected_target_id"]:
            readiness_reasons.append("target_uuid_mismatch")
        if not target_resolution["matches_set_id"]:
            readiness_reasons.append("pokemon_api_set_id_mismatch")

        if has_any_persisted and not explore_probe["resolved"]:
            readiness_reasons.append("explore_payload_resolution_failed_with_existing_data")

        ready = len(readiness_reasons) == 0
        if not ready:
            failures.extend(f"{set_id}: {reason}" for reason in readiness_reasons)

        per_set[set_id] = {
            "target_resolution": target_resolution,
            "presence_checks": {
                "simulation_latest_by_target": {
                    "row_found": simulation_latest["row_found"],
                    "selected_run_id": (simulation_latest["row"] or {}).get("calculation_run_id"),
                },
                "calculation_runs": {
                    "row_found": calculation_runs["row_found"],
                    "selected_run_id": (calculation_runs["row"] or {}).get("id"),
                },
                "explore_rip_statistics_latest": {
                    "row_found": rip_latest["row_found"],
                    "selected_run_id": (rip_latest["row"] or {}).get("calculation_run_id"),
                },
            },
            "explore_payload_probe": explore_probe,
            "execute_readiness": {
                "ready": ready,
                "reasons": readiness_reasons,
                "has_existing_persisted_rows": has_any_persisted,
            },
        }

    payload: Dict[str, Any] = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "17C.2",
            "script": "audit_swsh_lane1_controlled_persistence_preflight.py",
            "elapsed_seconds": time.perf_counter() - started_at,
            "read_only": True,
            "no_writes_performed": True,
        },
        "target": {
            "allowlist": list(TARGET_ALLOWLIST),
        },
        "per_set": per_set,
        "safety_assertions": {
            "passed": len(failures) == 0,
            "failures": failures,
        },
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lane 1 regular SWSH controlled persistence preflight (read-only)")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH), help="JSON output path")
    parser.add_argument("--stdout", action="store_true", help="Print summary JSON to stdout")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    try:
        payload = run_swsh_lane1_controlled_persistence_preflight(
            json_output_path=Path(args.json_output),
        )
    except Exception as exc:
        print(f"[audit] status=failed error={type(exc).__name__}: {exc}")
        return 1

    failed_set_count = sum(
        1
        for row in (payload.get("per_set") or {}).values()
        if not (row.get("execute_readiness") or {}).get("ready")
    )

    summary = {
        "status": "passed" if payload.get("safety_assertions", {}).get("passed") else "failed",
        "allowlist": payload.get("target", {}).get("allowlist"),
        "failed_set_count": failed_set_count,
        "safety_failures": payload.get("safety_assertions", {}).get("failures", []),
    }

    print(f"[audit] status={summary['status']}")
    print(f"[audit] allowlist={summary['allowlist']}")
    print(f"[audit] failed_set_count={summary['failed_set_count']}")

    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
