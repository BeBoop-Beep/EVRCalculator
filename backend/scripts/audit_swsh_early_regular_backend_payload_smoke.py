"""Project 17D.3 backend-only payload smoke for early regular SWSH sets.

Checks get_explore_page_payload("set", <target_uuid>) for:
- payload resolution
- summary/meta/rip statistics presence
- pull-rate/source-reference payload presence
- source-status guardrails in bucket evidence
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


DEFAULT_JSON_PATH = Path("logs/audits/swsh_early_regular_backend_payload_smoke.json")

TARGETS = {
    "swsh1": {
        "set_name": "Sword & Shield",
        "canonical_key": "swordAndShield",
        "target_uuid": "cbc11b3c-0244-4fca-880f-68ebdd599894",
    },
    "swsh2": {
        "set_name": "Rebel Clash",
        "canonical_key": "rebelClash",
        "target_uuid": "759c09f8-8a1b-4212-be89-66088afa6893",
    },
    "swsh3": {
        "set_name": "Darkness Ablaze",
        "canonical_key": "darknessAblaze",
        "target_uuid": "3836457c-77dc-44b0-a72f-779b6dd78884",
    },
}

OUT_OF_SCOPE_BUCKET_KEYWORDS = (
    "amazing rare",
    "trainer gallery",
    "radiant",
    "vstar",
)


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().upper()


def _bucket_is_out_of_scope(normalized_bucket: str) -> bool:
    bucket = str(normalized_bucket or "").strip().lower()
    return any(keyword in bucket for keyword in OUT_OF_SCOPE_BUCKET_KEYWORDS)


def _extract_bucket_evidence_issues(evidence_rows: List[Dict[str, Any]]) -> List[str]:
    failures: List[str] = []
    for row in evidence_rows:
        source_ids = [str(item) for item in (row.get("source_ids") or [])]
        status = _normalize_status(row.get("source_status"))
        used_in_runtime = bool(row.get("used_in_runtime"))
        normalized_bucket = str(row.get("normalized_bucket") or "").lower()

        if any("thepricedex" in source_id.lower() for source_id in source_ids):
            if status != "SECONDARY_INDEX_ONLY":
                failures.append(
                    f"ThePriceDex row status must be SECONDARY_INDEX_ONLY (bucket={normalized_bucket}, status={status})"
                )
            if status == "SOURCE_DIRECT":
                failures.append(
                    f"ThePriceDex row must not be SOURCE_DIRECT (bucket={normalized_bucket})"
                )

        if _bucket_is_out_of_scope(normalized_bucket):
            if status == "SOURCE_DIRECT":
                failures.append(
                    f"Out-of-scope bucket must not be SOURCE_DIRECT (bucket={normalized_bucket})"
                )
            if used_in_runtime:
                failures.append(
                    f"Out-of-scope bucket must remain reference-only (bucket={normalized_bucket})"
                )

    return failures


def run_swsh_early_regular_backend_payload_smoke(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
) -> Dict[str, Any]:
    started_at = time.perf_counter()

    per_set: Dict[str, Dict[str, Any]] = {}
    global_failures: List[str] = []

    for set_id, target in TARGETS.items():
        target_uuid = target["target_uuid"]

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
        references_present = _is_mapping(references_payload)
        bucket_evidence_rows = (
            list(references_payload.get("bucket_evidence") or [])
            if references_present
            else []
        )

        source_references_present = references_present and bool(references_payload.get("sources"))
        bucket_evidence_present = references_present and len(bucket_evidence_rows) > 0

        source_caveats = []
        if references_present:
            source_caveats = list(references_payload.get("caveats") or [])
        source_caveats_present = len(source_caveats) > 0

        bucket_evidence_failures = _extract_bucket_evidence_issues(bucket_evidence_rows)

        metadata_sources = ((payload or {}).get("meta") or {}).get("sources") or {}
        pull_rate_references_source_state = str(metadata_sources.get("pull_rate_references") or "")

        pricedex_rows = [
            row
            for row in bucket_evidence_rows
            if any("thepricedex" in str(item).lower() for item in (row.get("source_ids") or []))
        ]
        thepricedex_secondary_index_only = bool(pricedex_rows) and all(
            _normalize_status(row.get("source_status")) == "SECONDARY_INDEX_ONLY"
            for row in pricedex_rows
        )
        thepricedex_not_source_direct = bool(pricedex_rows) and all(
            _normalize_status(row.get("source_status")) != "SOURCE_DIRECT"
            for row in pricedex_rows
        )

        unsupported_rows = [
            row for row in bucket_evidence_rows if _bucket_is_out_of_scope(str(row.get("normalized_bucket") or ""))
        ]
        out_of_scope_runtime_direct_present = any(
            _normalize_status(row.get("source_status")) == "SOURCE_DIRECT"
            or bool(row.get("used_in_runtime")) is True
            for row in unsupported_rows
        )
        unsupported_reference_only = (
            True
            if not unsupported_rows
            else all(
                _normalize_status(row.get("source_status")) != "SOURCE_DIRECT"
                and bool(row.get("used_in_runtime")) is False
                for row in unsupported_rows
            )
        )

        set_failures: List[str] = []
        if not resolved:
            set_failures.append(f"payload resolve failed: {error_code}: {error_message}")
        if not summary_present:
            set_failures.append("summary missing")
        if not meta_present:
            set_failures.append("meta missing")
        if not rip_statistics_present:
            set_failures.append("rip_statistics missing")
        if pull_rate_references_source_state == "UNAVAILABLE_FOR_SET":
            set_failures.append("pull_rate_references source state is UNAVAILABLE_FOR_SET")
        if not source_references_present:
            set_failures.append("source references missing")
        if not bucket_evidence_present:
            set_failures.append("bucket evidence missing")
        if not source_caveats_present:
            set_failures.append("source caveats missing")
        if not pricedex_rows:
            set_failures.append("ThePriceDex guardrail cannot be verified because evidence rows are missing")
        elif not thepricedex_secondary_index_only:
            set_failures.append("ThePriceDex evidence rows must remain SECONDARY_INDEX_ONLY")
        elif not thepricedex_not_source_direct:
            set_failures.append("ThePriceDex evidence rows must not be SOURCE_DIRECT")
        if not unsupported_reference_only or out_of_scope_runtime_direct_present:
            set_failures.append(
                "Out-of-scope rows (Amazing Rare/Trainer Gallery/Radiant/VSTAR) must remain reference-only"
            )

        if references_present and bucket_evidence_failures:
            set_failures.extend(bucket_evidence_failures)

        per_set[set_id] = {
            "set_id": set_id,
            "set_name": target["set_name"],
            "canonical_key": target["canonical_key"],
            "target_uuid": target_uuid,
            "payload_resolved": resolved,
            "error_code": error_code,
            "error_message": error_message,
            "summary_present": summary_present,
            "meta_present": meta_present,
            "rip_statistics_present": rip_statistics_present,
            "source_references_present": bool(source_references_present),
            "bucket_evidence_present": bool(bucket_evidence_present),
            "source_caveats_present": bool(source_caveats_present),
            "pull_rate_references_source_state": pull_rate_references_source_state,
            "unsupported_rows_reference_only": bool(unsupported_reference_only),
            "out_of_scope_runtime_direct_present": bool(out_of_scope_runtime_direct_present),
            "thepricedex_secondary_index_only": bool(thepricedex_secondary_index_only),
            "thepricedex_not_source_direct": bool(thepricedex_not_source_direct),
            "set_failures": set_failures,
            "status": "passed" if not set_failures else "failed",
        }

        if set_failures:
            global_failures.extend(f"{set_id}: {failure}" for failure in set_failures)

    payload_out: Dict[str, Any] = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "17D.3",
            "script": "audit_swsh_early_regular_backend_payload_smoke.py",
            "elapsed_seconds": time.perf_counter() - started_at,
            "backend_only": True,
        },
        "target": {
            "allowlist": list(TARGETS.keys()),
            "targets": TARGETS,
        },
        "per_set": per_set,
        "safety_assertions": {
            "passed": len(global_failures) == 0,
            "failures": global_failures,
        },
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json.dumps(payload_out, indent=2, sort_keys=True), encoding="utf-8")
    return payload_out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Early regular SWSH backend payload smoke checks")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH), help="JSON output path")
    parser.add_argument("--stdout", action="store_true", help="Print summary JSON to stdout")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    try:
        payload = run_swsh_early_regular_backend_payload_smoke(
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
