"""Project 17E.3 backend payload smoke for swsh4 only.

Checks get_explore_page_payload("set", <target_uuid>) for:
- payload resolution and expected top-level sections
- pull_rate_references emission and source-reference evidence
- ThePriceDex secondary/index-only guardrails
- Amazing Rare evidence row stays reference-only
- caveat language reflects conservative runtime-limited exclusion policy
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.db.services.explore_page_service import ExplorePageError, get_explore_page_payload


DEFAULT_JSON_PATH = Path("logs/audits/vivid_voltage_backend_payload_smoke.json")

TARGET = {
    "set_id": "swsh4",
    "set_name": "Vivid Voltage",
    "canonical_key": "vividVoltage",
    "target_uuid": "26fedb88-87d7-487a-9f01-528d603c682e",
}

OUT_OF_SCOPE_BUCKET_KEYWORDS = (
    "trainer gallery",
    "radiant",
    "vstar",
)


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_bucket(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_thepricedex_row(row: Mapping[str, Any]) -> bool:
    source_ids = [str(item) for item in (row.get("source_ids") or [])]
    return any("thepricedex" in source_id.lower() for source_id in source_ids)


def _contains_any(text: str, keywords: List[str]) -> bool:
    normalized = str(text or "").strip().lower()
    return all(keyword in normalized for keyword in keywords)


def _bucket_is_out_of_scope(normalized_bucket: str) -> bool:
    bucket = _normalize_bucket(normalized_bucket)
    return any(keyword in bucket for keyword in OUT_OF_SCOPE_BUCKET_KEYWORDS)


def run_vivid_voltage_backend_payload_smoke(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
) -> Dict[str, Any]:
    started_at = time.perf_counter()

    set_failures: List[str] = []
    target_uuid = TARGET["target_uuid"]

    try:
        payload = get_explore_page_payload("set", target_uuid)
        resolved = True
        error_code = None
        error_message = None
    except ExplorePageError as exc:
        payload = None
        resolved = False
        error_code = exc.code
        error_message = exc.message
    except Exception as exc:
        payload = None
        resolved = False
        error_code = type(exc).__name__
        error_message = str(exc)

    summary_present = bool(_is_mapping((payload or {}).get("summary")))
    meta_present = bool(_is_mapping((payload or {}).get("meta")))
    rip_statistics_present = bool((payload or {}).get("rip_statistics"))

    references_payload = (payload or {}).get("pull_rate_references")
    pull_rate_references_present = _is_mapping(references_payload)
    source_references_present = bool(pull_rate_references_present and references_payload.get("sources"))

    bucket_evidence_rows = (
        list(references_payload.get("bucket_evidence") or [])
        if pull_rate_references_present
        else []
    )
    bucket_evidence_present = len(bucket_evidence_rows) > 0

    metadata_sources = ((payload or {}).get("meta") or {}).get("sources") or {}
    pull_rate_references_source_state = str(metadata_sources.get("pull_rate_references") or "")

    source_caveats = list((references_payload or {}).get("caveats") or [])
    source_caveats_present = len(source_caveats) > 0

    if not resolved:
        set_failures.append(f"payload resolve failed: {error_code}: {error_message}")
    if not summary_present:
        set_failures.append("summary missing")
    if not meta_present:
        set_failures.append("meta missing")
    if not rip_statistics_present:
        set_failures.append("rip_statistics missing")
    if not pull_rate_references_present:
        set_failures.append("pull_rate_references missing")
    if pull_rate_references_source_state == "UNAVAILABLE_FOR_SET":
        set_failures.append("pull_rate_references source state is UNAVAILABLE_FOR_SET")
    if not source_references_present:
        set_failures.append("source references missing")
    if not bucket_evidence_present:
        set_failures.append("bucket evidence missing")

    pricedex_rows = [row for row in bucket_evidence_rows if _is_thepricedex_row(row)]
    thepricedex_secondary_index_only = bool(pricedex_rows) and all(
        _normalize_status(row.get("source_status")) == "SECONDARY_INDEX_ONLY"
        for row in pricedex_rows
    )
    thepricedex_not_source_direct = bool(pricedex_rows) and all(
        _normalize_status(row.get("source_status")) != "SOURCE_DIRECT"
        for row in pricedex_rows
    )

    if not pricedex_rows:
        set_failures.append("ThePriceDex guardrail cannot be verified because evidence rows are missing")
    elif not thepricedex_secondary_index_only:
        set_failures.append("ThePriceDex evidence rows must remain SECONDARY_INDEX_ONLY")
    elif not thepricedex_not_source_direct:
        set_failures.append("ThePriceDex evidence rows must not be SOURCE_DIRECT")

    amazing_rare_rows = [
        row for row in bucket_evidence_rows if _normalize_bucket(row.get("normalized_bucket")) == "amazing rare"
    ]
    amazing_rare_reference_row_exists = len(amazing_rare_rows) > 0
    amazing_rare_provisional_directional = bool(amazing_rare_rows) and all(
        _normalize_status(row.get("source_status")) == "PROVISIONAL_DIRECTIONAL"
        for row in amazing_rare_rows
    )
    amazing_rare_used_in_runtime_false = bool(amazing_rare_rows) and all(
        bool(row.get("used_in_runtime")) is False
        for row in amazing_rare_rows
    )
    amazing_rare_not_runtime_direct = bool(amazing_rare_rows) and all(
        _normalize_status(row.get("source_status")) != "SOURCE_DIRECT"
        for row in amazing_rare_rows
    )

    if not amazing_rare_reference_row_exists:
        set_failures.append("Amazing Rare evidence row missing")
    elif not amazing_rare_provisional_directional:
        set_failures.append("Amazing Rare source_status must remain PROVISIONAL_DIRECTIONAL")
    elif not amazing_rare_used_in_runtime_false:
        set_failures.append("Amazing Rare used_in_runtime must remain false")
    elif not amazing_rare_not_runtime_direct:
        set_failures.append("Amazing Rare must not be SOURCE_DIRECT")

    out_of_scope_rows = [
        row
        for row in bucket_evidence_rows
        if _bucket_is_out_of_scope(str(row.get("normalized_bucket") or ""))
    ]
    out_of_scope_not_runtime_direct = (
        True
        if not out_of_scope_rows
        else all(
            _normalize_status(row.get("source_status")) != "SOURCE_DIRECT"
            and bool(row.get("used_in_runtime")) is False
            for row in out_of_scope_rows
        )
    )
    if not out_of_scope_not_runtime_direct:
        set_failures.append("Trainer Gallery/Radiant/VSTAR rows must not be runtime-direct")

    caveats_text = " ".join(str(item or "") for item in source_caveats).strip().lower()
    caveats_include_runtime_limited = "runtime-limited" in caveats_text or "runtime limited" in caveats_text
    caveats_include_conservative = "conservative" in caveats_text
    caveats_include_amazing_rare_exclusion = (
        ("amazing rare" in caveats_text)
        and ("exclude" in caveats_text or "excluded" in caveats_text)
    )
    caveats_present = bool(source_caveats_present) and (
        (caveats_include_runtime_limited or caveats_include_conservative)
        and caveats_include_amazing_rare_exclusion
    )
    if not caveats_present:
        set_failures.append(
            "source caveats must mention runtime-limited conservative exclusion of Amazing Rare"
        )

    per_set = {
        TARGET["set_id"]: {
            "set_id": TARGET["set_id"],
            "set_name": TARGET["set_name"],
            "canonical_key": TARGET["canonical_key"],
            "target_uuid": TARGET["target_uuid"],
            "payload_resolved": resolved,
            "error_code": error_code,
            "error_message": error_message,
            "summary_present": summary_present,
            "meta_present": meta_present,
            "rip_statistics_present": rip_statistics_present,
            "pull_rate_references_present": bool(pull_rate_references_present),
            "source_references_present": bool(source_references_present),
            "bucket_evidence_present": bool(bucket_evidence_present),
            "pull_rate_references_source_state": pull_rate_references_source_state,
            "thepricedex_secondary_index_only": bool(thepricedex_secondary_index_only),
            "thepricedex_not_source_direct": bool(thepricedex_not_source_direct),
            "amazing_rare_reference_row_exists": bool(amazing_rare_reference_row_exists),
            "amazing_rare_provisional_directional": bool(amazing_rare_provisional_directional),
            "amazing_rare_used_in_runtime_false": bool(amazing_rare_used_in_runtime_false),
            "amazing_rare_not_runtime_direct": bool(amazing_rare_not_runtime_direct),
            "out_of_scope_rows_not_runtime_direct": bool(out_of_scope_not_runtime_direct),
            "source_caveats_present": bool(source_caveats_present),
            "source_caveats_runtime_limited_conservative_amazing_rare": bool(caveats_present),
            "set_failures": set_failures,
            "status": "passed" if not set_failures else "failed",
        }
    }

    payload_out: Dict[str, Any] = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "17E.3",
            "script": "audit_vivid_voltage_backend_payload_smoke.py",
            "elapsed_seconds": time.perf_counter() - started_at,
            "backend_only": True,
        },
        "target": {
            "allowlist": [TARGET["set_id"]],
            "target": TARGET,
        },
        "per_set": per_set,
        "safety_assertions": {
            "passed": len(set_failures) == 0,
            "failures": [f"{TARGET['set_id']}: {failure}" for failure in set_failures],
        },
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json.dumps(payload_out, indent=2, sort_keys=True), encoding="utf-8")
    return payload_out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Vivid Voltage backend payload smoke checks")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH), help="JSON output path")
    parser.add_argument("--stdout", action="store_true", help="Print summary JSON to stdout")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    try:
        payload = run_vivid_voltage_backend_payload_smoke(
            json_output_path=Path(args.json_output),
        )
    except Exception as exc:
        print(f"[smoke] status=failed error={type(exc).__name__}: {exc}")
        return 1

    failed_set_count = sum(
        1
        for row in (payload.get("per_set") or {}).values()
        if str((row or {}).get("status") or "").lower() != "passed"
    )

    summary = {
        "status": "passed" if payload.get("safety_assertions", {}).get("passed") else "failed",
        "allowlist": payload.get("target", {}).get("allowlist"),
        "failed_set_count": failed_set_count,
        "safety_failures": payload.get("safety_assertions", {}).get("failures", []),
    }

    print(f"[smoke] status={summary['status']}")
    print(f"[smoke] allowlist={summary['allowlist']}")
    print(f"[smoke] failed_set_count={summary['failed_set_count']}")

    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
