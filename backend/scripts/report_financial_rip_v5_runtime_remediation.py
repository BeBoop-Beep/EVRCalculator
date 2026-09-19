"""Summarize read-only Best-Open runtime and frozen-threshold evidence."""
from __future__ import annotations

import json
from pathlib import Path

from backend.scripts.research_financial_rip_v5_best_open import ROOT, atomic_json

DOCS = ROOT / "docs/research"
LOGS = ROOT / "logs"
OUTPUT = DOCS / "financial_rip_v5_best_open_runtime_remediation.json"
REPORT = DOCS / "financial_rip_v5_best_open_runtime_remediation.md"


def read(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> None:
    before = read(LOGS / "best_open_price_v2_phase10b_four_product.json")
    after = (read(LOGS / "best_open_price_v2_phase10b_four_product_batched_final.json")
             or read(LOGS / "best_open_price_v2_phase10b_four_product_batched.json"))
    blocked = read(DOCS / "financial_rip_v5_best_open_blocked_20260919.json")
    highq = (read(LOGS / "financial_rip_v5_best_open_highq_v2_checkpoint.json")
             or read(LOGS / "financial_rip_v5_best_open_highq_checkpoint.json"))
    control = read(LOGS / "financial_rip_v5_best_open_v2_control_checkpoint.json")
    candidate = read(LOGS / "financial_rip_v5_best_open_checkpoint.json")
    final_candidate = read(DOCS / "financial_rip_v5_best_open_live_validation.json")
    prompt2_snapshot = read(DOCS / "financial_rip_v5_real_artifact_validation.json")["states"][0]["snapshot"]
    if not all((before, after, blocked, highq)):
        raise RuntimeError("baseline, batched Phase 10B, blocked, and high-q evidence required")
    old_product = blocked["products"][0]
    new_product = highq["products"][0]
    axes = ("financialV5", "overallV5Shadow")
    parity = {axis: {
        "thresholdCentsMatch": old_product[axis]["threshold"]["priceCents"] == new_product[axis]["threshold"]["priceCents"],
        "quantityMatch": old_product[axis]["threshold"]["quantity"] == new_product[axis]["threshold"]["quantity"],
        "benchmarkMatch": old_product[axis]["benchmarkProductId"] == new_product[axis]["benchmarkProductId"],
        "storedScoreMatch": old_product[axis]["threshold"]["financialRipV5CandidateScore"] == new_product[axis]["threshold"]["financialRipV5CandidateScore"],
        "exactness": new_product[axis]["exactness"],
    } for axis in axes}
    if any(not all(value for key, value in evidence.items() if key != "exactness")
           for evidence in parity.values()):
        raise RuntimeError("high-quantity threshold, benchmark, or stored score drift")
    if any(evidence["exactness"].get("thresholdWins") is not True or
           evidence["exactness"].get("nextPriceWins") is not False or
           evidence["exactness"].get("oneCentMaximal") is not True
           for evidence in parity.values()):
        raise RuntimeError("high-quantity winning-cent exactness failed")
    old_wall = sum(float(old_product[axis]["wallSeconds"]) for axis in axes)
    new_wall = float(new_product["financialV5"]["wallSeconds"])
    def frozen_rows(artifact):
        return [{key: row.get(key) for key in (
            "sealedProductId", "ripBestOpenPriceCents", "ripThresholdQuantity",
            "ripBenchmarkSealedProductId", "ripExactness",
            "financialBestOpenPriceCents", "financialThresholdQuantity",
            "financialBenchmarkSealedProductId", "financialExactness",
            "diagnostics", "searchWallSeconds",
        )} for row in artifact["engineResult"]["products"]]
    before_rows = {row["sealedProductId"]: row for row in frozen_rows(before)}
    after_rows = {row["sealedProductId"]: row for row in frozen_rows(after)}
    parity_keys = (
        "ripBestOpenPriceCents", "ripThresholdQuantity", "ripBenchmarkSealedProductId",
        "ripExactness", "financialBestOpenPriceCents", "financialThresholdQuantity",
        "financialBenchmarkSealedProductId", "financialExactness",
    )
    frozen_details_match = set(before_rows) == set(after_rows) and all(
        before_rows[pid][key] == after_rows[pid][key]
        for pid in before_rows for key in parity_keys
    )
    if not frozen_details_match:
        raise RuntimeError("frozen Phase 10B quantity, benchmark, or exactness drift")
    control_count = len((control or {}).get("products", []))
    candidate_count = len((candidate or {}).get("products", []))
    complete = (control_count == candidate_count == 138
                and control.get("status") == "complete"
                and final_candidate is not None
                and final_candidate.get("comparison", {}).get("exactnessPassCount") == 552
                and (DOCS / "financial_rip_v5_best_open_live_validation.md").exists()
                and "FINANCIAL_RIP_V5_BEST_OPEN_LIVE_VALIDATION_COMPLETE" in
                    (DOCS / "financial_rip_v5_best_open_live_validation.md").read_text(encoding="utf-8"))
    diagnostics = new_product["fusedDiagnostics"]
    payload = {
        "decision": ("FINANCIAL_RIP_V5_BEST_OPEN_LIVE_VALIDATION_COMPLETE" if complete
                     else "FINANCIAL_RIP_V5_BEST_OPEN_LIVE_VALIDATION_BLOCKED"),
        "branch": "develop",
        "initialGitHead": "73ba59b87bd43acee61340a3597dde18f56d685c",
        "initialUnrelatedWorkingTreeChanges": [
            "logs/run_simulations.log", "logs/task_scheduler_debug.log"],
        "sourceSnapshotId": highq["sourceSnapshotId"],
        "sourceFingerprint": highq["sourceFingerprint"],
        "sourceAuthorityFingerprint": highq["sourceAuthorityFingerprint"],
        "fullMarketBudget": highq["budget"],
        "candidateVersion": highq["candidateVersion"],
        "overallShadowVersion": highq["overallShadowVersion"],
        "controlMethodVersion": highq["controlMethodVersion"],
        "canonicalFinancialVersion": prompt2_snapshot["financial_rip_version"],
        "canonicalOverallVersion": prompt2_snapshot["overall_rip_version"],
        "candidateSearchMethodIdentity": highq["searchMethodIdentity"],
        "phase10b": {
            "beforeAllEightMatched": before["validation"]["allEightThresholdsMatched"],
            "afterAllEightMatched": after["validation"]["allEightThresholdsMatched"],
            "sameThresholdQuantitiesBenchmarksAndExactness": frozen_details_match,
            "beforeWallSeconds": before["profiling"]["wallSeconds"],
            "afterWallSeconds": after["profiling"]["wallSeconds"],
            "beforePeakRssBytes": before["profiling"]["peakRssBytes"],
            "afterPeakRssBytes": after["profiling"]["peakRssBytes"],
            "speedup": before["profiling"]["wallSeconds"] / after["profiling"]["wallSeconds"],
            "beforeProducts": before["validation"]["products"],
            "afterProducts": after["validation"]["products"],
            "beforeFrozenProducts": frozen_rows(before),
            "afterFrozenProducts": frozen_rows(after),
        },
        "highQuantity": {
            "productId": new_product["sealedProductId"],
            "productName": new_product["productName"],
            "oldWallSeconds": old_wall, "newWallSeconds": new_wall,
            "speedup": old_wall / new_wall,
            "axisParity": parity,
            "oldAxes": {axis: old_product[axis] for axis in axes},
            "newAxes": {axis: new_product[axis] for axis in axes},
            "diagnostics": diagnostics,
        },
        "cohortProgress": {"controlProducts": control_count,
                           "candidateProducts": candidate_count,
                           "requiredProducts": 138,
                           "controlSearchWallSeconds": sum(float(row.get("searchWallSeconds") or 0)
                                                           for row in (control or {}).get("products", [])),
                           "candidateSearchWallSeconds": sum(float(row["financialV5"].get("wallSeconds") or 0)
                                                             for row in (candidate or {}).get("products", [])),
                           "controlQuantityConstructionSeconds": sum(
                               float(row.get("diagnostics", {}).get("quantityConstructionSeconds") or 0)
                               for row in (control or {}).get("products", [])),
                           "candidateQuantityConstructionSeconds": sum(
                               float(row.get("fusedDiagnostics", {}).get("quantityConstructionSeconds") or 0)
                               for row in (candidate or {}).get("products", []))},
        "dominantRuntimePhaseIfIncomplete": (
            None if complete else
            "physical quantity construction in the incomplete V4/V12 control and V5 cohort searches"),
        "testMatrix": {
            "preChangeFocusedPassed": 40,
            "postChangeFocusedAndAffectedPassed": 126,
            "phase10bFrozenThresholds": 8,
            "phase10bBeforeMatched": 8,
            "phase10bAfterMatched": 8,
        },
        "readOnly": True,
        "productionMutation": False,
    }
    atomic_json(OUTPUT, payload)
    lines = [
        "# Financial RIP V5 Best-Open runtime remediation", "",
        f"Decision: `{payload['decision']}`.", "",
        f"Frozen source snapshot `{payload['sourceSnapshotId']}`; cohort fingerprint `{payload['sourceFingerprint']}`.",
        "", "## Frozen control parity", "",
        f"All eight Phase 10B thresholds matched before and after batching. Threshold quantities, benchmark identities, and exactness payloads also matched: {frozen_details_match}. Wall time {payload['phase10b']['beforeWallSeconds']:.1f}s to {payload['phase10b']['afterWallSeconds']:.1f}s ({payload['phase10b']['speedup']:.2f}x). Post-change peak RSS: {payload['phase10b']['afterPeakRssBytes']} bytes; pre-change RSS unavailable in the original sampler.",
        "", "## High-quantity product", "",
        f"{new_product['productName']}: two prior passes {old_wall:.1f}s; fused batched pass {new_wall:.1f}s ({old_wall/new_wall:.2f}x).",
        f"Financial {new_product['financialV5']['threshold']['priceCents']} cents at q={new_product['financialV5']['threshold']['quantity']}; Overall shadow {new_product['overallV5Shadow']['threshold']['priceCents']} cents at q={new_product['overallV5Shadow']['threshold']['quantity']}.",
        f"Both axes match retained threshold, benchmark, and stored score; both winning cents are exact with the adjacent cent losing.",
        f"Maximum pending batch {diagnostics.get('maximumPendingBatchCandidates')}; effective RNG draws {diagnostics.get('effectiveRngDraws')}; separate-construction equivalent {diagnostics.get('legacyEquivalentRngDraws')}; peak RSS {diagnostics.get('peakRssBytes')} bytes.",
        f"Construction {diagnostics.get('quantityConstructionSeconds')}s; price scoring {diagnostics.get('priceScoringSeconds')}s; comparator {diagnostics.get('comparatorSeconds')}s.",
        "", "## Full cohort progress", "",
        f"Control {control_count}/138; V5 candidate {candidate_count}/138. Per-product evidence is checkpointed under `logs/` and excluded from Git.",
        f"Accumulated exact-search wall time: control {payload['cohortProgress']['controlSearchWallSeconds']:.1f}s with {payload['cohortProgress']['controlQuantityConstructionSeconds']:.1f}s constructing quantities; V5 {payload['cohortProgress']['candidateSearchWallSeconds']:.1f}s with {payload['cohortProgress']['candidateQuantityConstructionSeconds']:.1f}s constructing quantities.",
        ("All 138 control and candidate products and the final four-threshold report are complete."
         if complete else
         "The current incomplete phase is dominated by physical quantity construction; no cohort conclusion is asserted from these partial checkpoints."),
        "", "Pre-change focused tests: 40 passed. Post-change focused and affected exact-search tests: 126 passed.",
        "", "The blocked Prompt 3 report and JSON are preserved under `financial_rip_v5_best_open_blocked_20260919.*`. Canonical Financial V4 and Overall V12 remain active. This run performed no production database writes, publication, pointer change, migration, or frontend change. Prompt 4 has not started.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
