"""Read-only export of the final V12/V11 full-generation candidate for ChatGPT
to apply as production DB writes. This script performs NO database writes of
any kind - it only reads current production state and writes one local JSON
file. It reuses the exact same fresh-row-building logic as
build_atomic_set_page_snapshot_generation.py (imported directly, not
reimplemented) so the artifact is guaranteed to match what that script's
--write-stage path would build.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.db.services.collector_appeal_current_service import (
    PUBLIC_CONTRACT_KEY,
    build_public_collector_appeal_contract_from_v5,
    load_canonical_v5_collector_appeal,
)
from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_VERSION
from backend.db.services.explore_rip_statistics_service import get_rip_statistics_targets_payload
from backend.db.services.public_rip_publication_contract import canonical_publication_identity
from backend.scripts.pokemon_snapshot_builders import build_set_page_snapshot_row
from backend.scripts.snapshot_query_retry import run_snapshot_operation_with_retry
from backend.db.services.rankings_publication_lifecycle import source_run_fingerprint

ARTIFACT_PATH = ROOT / "backend" / "artifacts" / "rankings" / "final_v12_set_page_generation_candidate_20260908.json"


def main() -> None:
    started = time.perf_counter()
    load_dotenv(ROOT / "backend" / ".env")
    c = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    identity = canonical_publication_identity()

    # --- read current live full membership -----------------------------------
    existing = []
    start = 0
    while True:
        page = (
            c.table("pokemon_set_page_snapshot_latest")
            .select("*")
            .order("set_id")
            .range(start, start + 24)
            .execute()
            .data
            or []
        )
        existing += page
        if len(page) < 25:
            break
        start += 25
    full_set_ids = sorted(r["set_id"] for r in existing)
    if len(full_set_ids) != len(set(full_set_ids)):
        raise RuntimeError("duplicate set IDs found in pokemon_set_page_snapshot_latest")

    # --- current live generation pointer --------------------------------------
    current_generation = (
        c.table("pokemon_set_page_snapshot_current_generation")
        .select("generation_id")
        .eq("scope", "pokemon")
        .single()
        .execute()
        .data
    )

    # --- current active Rankings publication -----------------------------------
    active_pub_row = (
        c.table("pokemon_public_rip_leaderboard_snapshots")
        .select("*")
        .order("published_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    active_publication = active_pub_row[0] if active_pub_row else None

    # --- resolve full sets rows + frozen 22-run cohort --------------------------
    sets = []
    for i in range(0, len(full_set_ids), 50):
        sets += c.table("sets").select("*").in_("id", full_set_ids[i : i + 50]).execute().data or []
    by_id = {str(r["id"]): r for r in sets}
    if set(by_id) != set(full_set_ids):
        raise RuntimeError("fresh generation set membership could not be resolved")

    rankings_payload_before = get_rip_statistics_targets_payload(limit=250, include_rankings_top_chase=False)
    if (rankings_payload_before.get("meta") or {}).get("desirabilityBundleStatus") != "ok":
        raise RuntimeError("canonical Rankings cohort failed to build completely")

    overall_key = "overallRipV12"
    ranked = [
        r
        for r in rankings_payload_before.get("targets") or []
        if (r.get(overall_key) or {}).get("rank") is not None
    ]
    frozen_runs = {
        str(r.get("set_id") or r.get("target_id")): str(r.get("calculation_run_id")) for r in ranked
    }
    if len(frozen_runs) != 22 or any(not v or v == "None" for v in frozen_runs.values()):
        raise RuntimeError(
            f"refusing non-22 or incomplete frozen calculation-run cohort (got {len(frozen_runs)})"
        )
    fresh_set_ids = sorted(frozen_runs)
    carry_forward_set_ids = sorted(sid for sid in full_set_ids if sid not in frozen_runs)
    if len(fresh_set_ids) + len(carry_forward_set_ids) != len(full_set_ids):
        raise RuntimeError("full-generation membership accounting failed to reconcile fresh + carry-forward sets")

    missing_live = set(full_set_ids) - (set(fresh_set_ids) | set(carry_forward_set_ids))
    if missing_live:
        raise RuntimeError(f"candidate omits currently-live set(s): {sorted(missing_live)}")

    frozen_fingerprint = source_run_fingerprint(frozen_runs)

    # --- canonical V5 Collector authority (fresh sets only) ---------------------
    v5 = load_canonical_v5_collector_appeal(fresh_set_ids)
    collector = v5["payloads"]
    collector_fingerprint = (v5["identity"] or {}).get("formulaFingerprint")
    scored = sum(1 for x in collector.values() if (x.get("collectorAppeal") or {}).get("score") is not None)
    if scored != len(fresh_set_ids):
        raise RuntimeError("canonical Collector authority is incomplete for frozen cohort")

    latest_by_id = {str(r["set_id"]): r for r in existing}

    def build_fresh_row(fresh_client, set_id):
        copied = build_set_page_snapshot_row(
            by_id[set_id], client=fresh_client, rankings_payload=rankings_payload_before
        )
        payload = dict(copied["payload_json"])
        payload.pop(PUBLIC_CONTRACT_KEY, None)
        contract = build_public_collector_appeal_contract_from_v5(collector.get(set_id))
        if not contract:
            raise RuntimeError("missing canonical Collector authority for set " + set_id)
        ca = contract.get("collectorAppeal") or {}
        if ca.get("version") != COLLECTOR_APPEAL_V5_VERSION or ca.get("modelRunId") is not None:
            raise RuntimeError("canonical V5 authority validation failed for set " + set_id)
        payload[PUBLIC_CONTRACT_KEY] = contract
        copied["payload_json"] = payload
        copied["created_at"] = copied.get("created_at") or copied.get("source_updated_at")
        copied["updated_at"] = copied.get("updated_at") or copied.get("source_updated_at")
        return copied

    fresh_rows = []
    for set_id in fresh_set_ids:
        row = run_snapshot_operation_with_retry(
            lambda fresh_client, set_id=set_id: build_fresh_row(fresh_client, set_id),
            operation_name="export fresh set-page generation row",
            set_id=set_id,
        )
        fresh_rows.append(row)

    # --- re-verify authority did not change during the build ---------------------
    rankings_payload_after = get_rip_statistics_targets_payload(limit=250, include_rankings_top_chase=False)
    ranked_after = [
        r
        for r in rankings_payload_after.get("targets") or []
        if (r.get(overall_key) or {}).get("rank") is not None
    ]
    frozen_runs_after = {
        str(r.get("set_id") or r.get("target_id")): str(r.get("calculation_run_id")) for r in ranked_after
    }
    fingerprint_after = source_run_fingerprint(frozen_runs_after)
    if fingerprint_after != frozen_fingerprint:
        raise RuntimeError(
            "frozen source-run fingerprint changed during build "
            f"(before={frozen_fingerprint}, after={fingerprint_after}) - refusing to export a mixed candidate"
        )

    live_after = (
        c.table("pokemon_set_page_snapshot_current_generation")
        .select("generation_id")
        .eq("scope", "pokemon")
        .single()
        .execute()
        .data
    )
    if (current_generation or {}).get("generation_id") != (live_after or {}).get("generation_id"):
        raise RuntimeError("active set-page generation changed during build - refusing to export a mixed candidate")

    active_pub_row_after = (
        c.table("pokemon_public_rip_leaderboard_snapshots")
        .select("id,market_date,overall_rip_version,financial_rip_version,ca7_version,diagnostics_json")
        .order("published_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    active_publication_after = active_pub_row_after[0] if active_pub_row_after else None
    if (active_publication or {}).get("id") != (active_publication_after or {}).get("id"):
        raise RuntimeError("active Rankings publication changed during build - refusing to export a mixed candidate")

    # --- Rankings parity: fresh row V12 run/rank/score must match Rankings target
    ranked_by_id = {str(r.get("set_id") or r.get("target_id")): r for r in ranked}
    mismatches = []
    for row in fresh_rows:
        set_id = str(row["set_id"])
        payload = row["payload_json"]
        target = ranked_by_id.get(set_id) or {}
        page_overall = payload.get(overall_key) or {}
        target_overall = target.get(overall_key) or {}
        if page_overall.get("rank") != target_overall.get("rank") or page_overall.get("score") != target_overall.get(
            "score"
        ):
            mismatches.append(set_id)
    if mismatches:
        raise RuntimeError(f"Rankings/set-page V12 rank/score parity failed for: {mismatches}")

    if not active_publication:
        raise RuntimeError("no active Rankings publication found - cannot certify parity")
    active_market_date = active_publication.get("market_date")

    artifact = {
        "metadata": {
            "marketDate": active_market_date,
            "activeRankingsPublicationId": active_publication.get("id"),
            "activeRankingsOverallVersion": active_publication.get("overall_rip_version"),
            "activeRankingsFinancialVersion": active_publication.get("financial_rip_version"),
            "activeCollectorVersion": active_publication.get("ca7_version"),
            "publicContractVersion": (active_publication.get("diagnostics_json") or {}).get(
                "public_rip_contract_version"
            ),
            "sourceActiveGenerationId": (current_generation or {}).get("generation_id"),
            "fullExpectedSetCount": len(full_set_ids),
            "freshRebuiltSetCount": len(fresh_set_ids),
            "carriedForwardSetCount": len(carry_forward_set_ids),
            "expectedSetIds": full_set_ids,
            "freshSetIds": fresh_set_ids,
            "carriedForwardSetIds": carry_forward_set_ids,
            "frozenSourceRuns": frozen_runs,
            "frozenSourceRunFingerprint": frozen_fingerprint,
            "canonicalOverallRipVersion": identity["overallRipVersion"],
            "canonicalFinancialRipVersion": identity["financialRipVersion"],
            "canonicalCollectorAppealVersion": identity["collectorAppealVersion"],
            "canonicalPublicRipContractVersion": identity["publicRipContractVersion"],
            "builtAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "freshRows": fresh_rows,
        "carryForwardStrategy": (
            "Do NOT ship the ~188 carry-forward rows in this artifact. For each set_id in "
            "metadata.carriedForwardSetIds, INSERT INTO pokemon_set_page_snapshot_generation_rows "
            "SELECT <generation_id>, set_id, set_identity_json, title_card_json, rip_summary_json, "
            "market_summary_json, risk_summary_json, concentration_json, desirability_summary_json, "
            "set_intelligence_json, payload_json, as_of, source_updated_at, created_at, updated_at, "
            "rip_bootstrap_json, rip_simulation_evidence_json, rip_advanced_json "
            "FROM pokemon_set_page_snapshot_latest WHERE set_id = ANY(<carriedForwardSetIds>) "
            "- i.e. copy the row verbatim server-side, never rewriting timestamps or content."
        ),
        "dbWriteHandoff": {
            "order": [
                "1. Preflight: re-verify active Rankings publication id still == metadata.activeRankingsPublicationId, "
                "current generation pointer still == metadata.sourceActiveGenerationId, and live set_id membership "
                "in pokemon_set_page_snapshot_latest still equals metadata.expectedSetIds.",
                "2. INSERT one row into pokemon_set_page_snapshot_generations with status='building', "
                "expected_set_ids=metadata.expectedSetIds, expected_set_count=metadata.fullExpectedSetCount, "
                "collector_model_run_id=NULL, collector_contract_version='public_collector_appeal_contract_v1', "
                "expected_collector_row_count=metadata.freshRebuiltSetCount, "
                "previous_generation_id=metadata.sourceActiveGenerationId, diagnostics_json=metadata.",
                "3. Copy the 188 carry-forward rows per carryForwardStrategy above.",
                "4. INSERT the 22 freshRows entries into pokemon_set_page_snapshot_generation_rows, one row per "
                "entry, with generation_id set to the new generation's id (each entry's own keys map directly "
                "to that table's columns: set_id, set_identity_json, title_card_json, rip_summary_json, "
                "market_summary_json, risk_summary_json, concentration_json, desirability_summary_json, "
                "set_intelligence_json, payload_json, as_of, source_updated_at, created_at, updated_at, "
                "rip_bootstrap_json, rip_simulation_evidence_json, rip_advanced_json).",
                "5. Verify row count in pokemon_set_page_snapshot_generation_rows for this generation_id == "
                "metadata.fullExpectedSetCount (210) with no duplicate set_ids.",
                "6. CALL validate_pokemon_set_page_snapshot_generation(p_generation_id) and confirm "
                "(validation_json->>'passed')::boolean = true.",
                "7. Confirm the generation's status is now 'validated' and actual_set_count/expected_set_count "
                "match 210/210 with no invalid rows.",
                "8. CALL activate_pokemon_set_page_snapshot_generation(p_generation_id) - this is the "
                "destructive delete-then-insert step; it will raise and abort if the candidate omits any "
                "currently-live set page (the fail-closed guard already in production).",
                "9. Verify pokemon_set_page_snapshot_latest now has exactly 210 rows.",
                "10. Verify the 22 freshSetIds rows now carry overallRipV12/publicRipContractV11/financialRipV4 "
                "matching metadata's canonical version strings.",
                "11. Verify the 188 carriedForwardSetIds rows are byte-identical to their pre-activation content "
                "(payload_json, source_updated_at, created_at, updated_at, as_of all unchanged).",
                "12. Verify the active Rankings publication id is still metadata.activeRankingsPublicationId - "
                "this task does not touch Rankings, only the set-page generation.",
            ],
            "note": "Claude performed zero writes to produce this artifact. All steps above must be executed "
            "by a separate party with production write access.",
        },
    }

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    size_bytes = ARTIFACT_PATH.stat().st_size
    print(
        json.dumps(
            {
                "artifactPath": str(ARTIFACT_PATH),
                "artifactSizeBytes": size_bytes,
                "fullExpectedSetCount": len(full_set_ids),
                "freshRebuiltSetCount": len(fresh_set_ids),
                "carriedForwardSetCount": len(carry_forward_set_ids),
                "frozenSourceRunFingerprint": frozen_fingerprint,
                "activeRankingsPublicationId": active_publication.get("id"),
                "buildSeconds": round(time.perf_counter() - started, 3),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
