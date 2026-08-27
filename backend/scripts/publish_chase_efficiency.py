"""Build, audit, report, and optionally publish canonical Chase Efficiency."""
from __future__ import annotations

import argparse
import json
import time

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.chase_efficiency_service import load_candidate, publish_candidate, validate_candidate


def run(*, market_date: str, commit: bool, client=None):
    total_started = time.perf_counter()
    client = client or create_service_role_client()
    source_telemetry = {"page_requests": 0}
    load_started = time.perf_counter()
    candidate = load_candidate(client, market_date=market_date, telemetry=source_telemetry)
    load_seconds = time.perf_counter() - load_started
    validation_started = time.perf_counter()
    failures = validate_candidate(candidate)
    validation_seconds = time.perf_counter() - validation_started
    rows = candidate["rows"]
    publication_payload_bytes = len(json.dumps(
        {"p_snapshot": candidate["snapshot"], "p_rows": rows},
        separators=(",", ":"), allow_nan=False, default=str,
    ).encode("utf-8"))
    serialized_rows = [json.dumps(row, separators=(",", ":"), allow_nan=False, default=str).encode("utf-8") for row in rows]
    verified_routes_bytes = sum(len(json.dumps(row.get("verified_routes"), separators=(",", ":"), default=str).encode("utf-8")) for row in rows)
    milestones_bytes = sum(len(json.dumps(row.get("milestones"), separators=(",", ":"), default=str).encode("utf-8")) for row in rows)
    report = {
        **candidate["snapshot"], "audit": "PASS" if not failures else "FAIL", "auditFailures": failures,
        "top25": [{k: row.get(k) for k in ("overall_rank","overall_cohort_size","card_name","canonical_rarity","chase_efficiency","probability","current_market_price","best_verified_pack_equivalent_cost","era_rank","era_cohort_size","set_rank","set_cohort_size","rarity_rank","rarity_cohort_size")} for row in rows[:25]],
        "topSIRs": [{"rank": r["rarity_rank"], "name": r["card_name"], "chaseEfficiency": r["chase_efficiency"]} for r in rows if r.get("canonical_rarity") == "Special Illustration Rare"][:25],
        "topIRs": [{"rank": r["rarity_rank"], "name": r["card_name"], "chaseEfficiency": r["chase_efficiency"]} for r in rows if r.get("canonical_rarity") == "Illustration Rare"][:25],
        "telemetry": {
            "candidateLoadSeconds": load_seconds,
            "sourcePageRequests": source_telemetry["page_requests"],
            "candidateValidationSeconds": validation_seconds,
            "eligibleRowCount": len(rows),
            "publicationPayloadBytes": publication_payload_bytes,
            "averageRowPayloadBytes": (sum(map(len, serialized_rows)) / len(serialized_rows)) if serialized_rows else 0,
            "largestRowPayloadBytes": max(map(len, serialized_rows), default=0),
            "verifiedRoutesPayloadBytes": verified_routes_bytes,
            "milestonesPayloadBytes": milestones_bytes,
            "rpcPublicationSeconds": None,
            "persistedAuditSeconds": None,
            "totalSeconds": None,
        },
    }
    if failures:
        report["telemetry"]["totalSeconds"] = time.perf_counter() - total_started
        return 1, report
    if commit:
        rpc_started = time.perf_counter()
        try:
            publication_telemetry = {"staging_requests": 0}
            report["snapshotId"] = publish_candidate(client, candidate, telemetry=publication_telemetry)
            report["telemetry"]["stagingRequests"] = publication_telemetry["staging_requests"]
        except Exception as exc:
            database_code = getattr(exc, "code", None)
            if database_code is None and getattr(exc, "args", None) and isinstance(exc.args[0], dict):
                database_code = exc.args[0].get("code")
            report["telemetry"]["rpcPublicationSeconds"] = time.perf_counter() - rpc_started
            report["telemetry"]["totalSeconds"] = time.perf_counter() - total_started
            report["publicationError"] = {
                "marketDate": market_date,
                "candidateRowCount": len(rows),
                "payloadBytes": publication_payload_bytes,
                "rpcElapsedSeconds": report["telemetry"]["rpcPublicationSeconds"],
                "databaseCode": database_code,
                "message": str(exc),
            }
            return 1, report
        report["telemetry"]["rpcPublicationSeconds"] = time.perf_counter() - rpc_started
        from backend.scripts.audit_chase_efficiency_publication import run_audit
        audit_started = time.perf_counter()
        persisted_audit = run_audit(client, market_date=market_date)
        report["telemetry"]["persistedAuditSeconds"] = time.perf_counter() - audit_started
        report["persistedAudit"] = persisted_audit
        if not persisted_audit.get("passed"):
            report["telemetry"]["totalSeconds"] = time.perf_counter() - total_started
            return 1, report
    report["telemetry"]["totalSeconds"] = time.perf_counter() - total_started
    return 0, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", required=True)
    mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--dry-run", action="store_true"); mode.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)
    code, report = run(market_date=args.market_date, commit=args.commit)
    print(json.dumps(report, indent=2, default=str)); return code


if __name__ == "__main__": raise SystemExit(main())
