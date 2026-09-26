"""EBAY_E2_9A: exact distinct-card coverage closure for COMBINED-IDENTITY-v2.

NON-CERTIFYING, MEASUREMENT ONLY. This script does not modify D3-v5,
IMAGE-v2, or COMBINED-IDENTITY-v2 semantics/thresholds in any way. It
re-runs the exact frozen per-row execution path E2.8 used
(`run_ebay_combined_identity_historical_diagnostic.build_gallery_from_resolution`,
the same `RESOLVE_MANIFEST_PATH`, frozen `ebay_d3_matcher_v5.classify_listing`,
and frozen `ebay_combined_identity_policy_v1.resolve_image_state` /
`has_text_contradiction`), scoped to only the rows that can possibly
contribute a new eligible accept under COMBINED-IDENTITY-v2:

    D3-v5 text_state == HIGH_CONFIDENCE  AND  no existing text contradiction

Every other row (REJECTED / MEDIUM_CONFIDENCE / AMBIGUOUS text, or a
HIGH_CONFIDENCE row a text contradiction already vetoes) cannot become
TIER_A or TIER_B under v2's own decision table (see
ebay_combined_identity_policy_v2.combine), so it is excluded from the
(real, network+model) per-row image pass -- not because its data is
missing, but because processing it cannot change the coverage answer.

For each scoped row this computes, using ONLY frozen code:
  - text_state         (ebay_d3_matcher_v5.classify_listing, frozen)
  - text_contradiction (ebay_combined_identity_policy_v1.has_text_contradiction, frozen)
  - image_state        (ebay_combined_identity_policy_v1.resolve_image_state,
                         which wraps the frozen IMAGE-v2 verify_by_retrieval)
  - combined_v1_state  (ebay_combined_identity_policy_v1.combine, frozen --
                         used ONLY to cross-check reproduction against the
                         already-frozen E2.8 aggregate cross-tab)
  - combined_v2_state  (ebay_combined_identity_policy_v2.combine, frozen --
                         the actual policy under evaluation)

and persists the per-row results plus exact card-coverage accounting.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts import ebay_combined_identity_policy_v1 as policy_v1
from backend.scripts import ebay_combined_identity_policy_v2 as policy_v2
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.run_ebay_combined_identity_historical_diagnostic import (
    QUEUE_PATHS,
    _listing_dict,
    _load_rows,
    _target_dict,
    build_gallery_from_resolution,
    classify_human_label,
)

NON_CERTIFYING_LABEL = "NON_CERTIFYING_EXACT_CARD_COVERAGE_MEASUREMENT"
TOTAL_TARGET_CARDS_PER_COHORT = 70

PER_ROW_OUTPUT_PATH = OUT / "ebay_e2_9a_exact_card_coverage_per_row.json"
SUMMARY_OUTPUT_PATH = OUT / "ebay_e2_9a_exact_card_coverage_summary.json"


def _is_scoped(text_state: str, contradiction: bool) -> bool:
    return text_state == "HIGH_CONFIDENCE" and not contradiction


def scope_rows(cohort_rows: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Pure-text scoping pass -- no network, no image model. Reused by both
    the runner and the row-count reporting/tests so the two can never
    silently drift apart.
    """
    scoped: dict[str, list[dict[str, Any]]] = {}
    for cohort, rows in cohort_rows.items():
        keep = []
        for row in rows:
            text_result = v5.classify_listing(_target_dict(row), _listing_dict(row))
            text_state = text_result["identity_state"]
            contradiction = policy_v1.has_text_contradiction(row)
            if _is_scoped(text_state, contradiction):
                keep.append({**row, "_text_state": text_state, "_text_contradiction": contradiction})
        scoped[cohort] = keep
    return scoped


def wilson(successes: int, total: int) -> list[float]:
    import math
    z = 1.959963984540054
    if not total:
        return [0.0, 0.0]
    p = successes / total
    d = 1 + z * z / total
    c = (p + z * z / (2 * total)) / d
    m = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return [round(c - m, 8), round(c + m, 8)]


def ratio(a: int, b: int) -> float:
    return round(a / b, 8) if b else 0.0


def run_scoped_rows(cohort: str, scoped: list[dict[str, Any]], gallery) -> list[dict[str, Any]]:
    out = []
    for row in scoped:
        text_state = row["_text_state"]
        contradiction = row["_text_contradiction"]
        image_result = policy_v1.resolve_image_state(gallery, row["canonical_card_id"], row.get("image_url", ""))
        image_state = image_result["image_identity_state"]

        v1_result = policy_v1.combine(text_state, image_state, text_row_fields=row)
        v2_result = policy_v2.combine(text_state, image_state, text_row_fields=row)

        human_raw = classify_human_label(row)
        human = {"yes": "YES", "no": "NO", "uncertain": "UNCERTAIN"}[human_raw]

        out.append({
            "row_id": row["benchmark_row_id"],
            "cohort": cohort,
            "canonical_card_id": row["canonical_card_id"],
            "human_truth": human,
            "text_state": text_state,
            "text_contradiction": contradiction,
            "image_state": image_state,
            "combined_v1_state": v1_result.combined_state,
            "combined_v2_state": v2_result.combined_state,
            "eligible_under_v2": v2_result.is_eligible,
            "tier": ("TIER_A" if v2_result.combined_state == policy_v2.TIER_A_IMAGE_VERIFIED
                     else "TIER_B" if v2_result.combined_state == policy_v2.TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED
                     else None),
            "true_eligible_accept": bool(v2_result.is_eligible and human == "YES"),
        })
    return out


def reproduction_check(per_row: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Recompute the frozen E2.8/E2.9 aggregate metrics from these
    freshly-resolved per-row results and compare against the frozen,
    already-committed E2.8 cross-tab counts (the same numbers reported in
    EBAY_E2_9_IMAGE_VETO_TIERED_IDENTITY_POLICY.md Sections 2-3/5/6/14/15).
    """
    frozen_expected = {
        "V4": {"tier_a": 115, "tier_b": 88, "mismatch_yes": 13, "mismatch_no": 0},
        "V5": {"tier_a": 107, "tier_b": 99, "mismatch_yes": 15, "mismatch_no": 0},
    }
    report = {}
    all_ok = True
    for cohort, rows in per_row.items():
        definitive = [r for r in rows if r["human_truth"] in ("YES", "NO")]
        tier_a = [r for r in definitive if r["combined_v2_state"] == policy_v2.TIER_A_IMAGE_VERIFIED]
        tier_b = [r for r in definitive if r["combined_v2_state"] == policy_v2.TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED]
        mismatch = [r for r in definitive if r["image_state"] == "MISMATCH"]
        mismatch_yes = [r for r in mismatch if r["human_truth"] == "YES"]
        mismatch_no = [r for r in mismatch if r["human_truth"] == "NO"]

        tier_a_fp = [r for r in tier_a if r["human_truth"] == "NO"]
        tier_b_fp = [r for r in tier_b if r["human_truth"] == "NO"]

        observed = {
            "tier_a": len(tier_a), "tier_b": len(tier_b),
            "mismatch_yes": len(mismatch_yes), "mismatch_no": len(mismatch_no),
        }
        expected = frozen_expected[cohort]
        matches = observed == expected
        all_ok = all_ok and matches and not tier_a_fp and not tier_b_fp

        report[cohort] = {
            "observed": observed, "expected": expected, "matches": matches,
            "tier_a_accepted": len(tier_a), "tier_a_true_accepts": len(tier_a) - len(tier_a_fp),
            "tier_a_false_accepts": len(tier_a_fp),
            "tier_a_precision": ratio(len(tier_a) - len(tier_a_fp), len(tier_a)),
            "tier_a_wilson_lower": wilson(len(tier_a) - len(tier_a_fp), len(tier_a))[0],
            "tier_b_accepted": len(tier_b), "tier_b_true_accepts": len(tier_b) - len(tier_b_fp),
            "tier_b_false_accepts": len(tier_b_fp),
            "tier_b_precision": ratio(len(tier_b) - len(tier_b_fp), len(tier_b)),
            "tier_b_wilson_lower": wilson(len(tier_b) - len(tier_b_fp), len(tier_b))[0],
            "combined_accepted": len(tier_a) + len(tier_b),
            "combined_true_accepts": (len(tier_a) - len(tier_a_fp)) + (len(tier_b) - len(tier_b_fp)),
            "combined_false_accepts": len(tier_a_fp) + len(tier_b_fp),
            "combined_precision": ratio(
                (len(tier_a) - len(tier_a_fp)) + (len(tier_b) - len(tier_b_fp)), len(tier_a) + len(tier_b)),
            "combined_wilson_lower": wilson(
                (len(tier_a) - len(tier_a_fp)) + (len(tier_b) - len(tier_b_fp)), len(tier_a) + len(tier_b))[0],
            "catastrophic_false_accepts": len(tier_a_fp) + len(tier_b_fp),
            "high_confidence_unverified_human_no": sum(
                1 for r in definitive
                if r["text_state"] == "HIGH_CONFIDENCE" and r["image_state"] == "UNVERIFIED" and r["human_truth"] == "NO"
            ),
        }
    report["_all_reproduced"] = all_ok
    return report


def exact_card_coverage(per_row: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    report = {}
    for cohort, rows in per_row.items():
        true_accepts = [r for r in rows if r["true_eligible_accept"]]
        tier_a_cards = {r["canonical_card_id"] for r in true_accepts if r["tier"] == "TIER_A"}
        tier_b_only_cards = {r["canonical_card_id"] for r in true_accepts if r["tier"] == "TIER_B"} - tier_a_cards
        covered_cards = tier_a_cards | tier_b_only_cards
        all_cards = {r["canonical_card_id"] for r in rows}
        # Uncovered = the full 70-card target universe minus covered, using
        # the canonical_card_id universe actually observed in this cohort's
        # queue (queue targets are drawn 1:1 from the 70-card cohort design).
        uncovered_cards = sorted(all_cards - covered_cards)

        report[cohort] = {
            "total_target_cards": TOTAL_TARGET_CARDS_PER_COHORT,
            "tier_a_covered_count": len(tier_a_cards),
            "tier_b_incremental_count": len(tier_b_only_cards),
            "total_covered_count": len(covered_cards),
            "exact_coverage": ratio(len(covered_cards), TOTAL_TARGET_CARDS_PER_COHORT),
            "tier_a_covered_card_ids": sorted(tier_a_cards),
            "tier_b_incremental_card_ids": sorted(tier_b_only_cards),
            "uncovered_card_ids": uncovered_cards,
        }
    return report


def four_gates(reproduction: dict[str, Any], coverage: dict[str, Any]) -> dict[str, Any]:
    gates = {}
    for cohort in ("V4", "V5"):
        rep = reproduction[cohort]
        cov = coverage[cohort]
        checks = {
            "accepted_precision_ge_0_99": rep["combined_precision"] >= 0.99,
            "wilson_lower_ge_0_98": rep["combined_wilson_lower"] >= 0.98,
            "card_coverage_ge_0_80": cov["exact_coverage"] >= 0.80,
            "catastrophic_false_accepts_eq_0": rep["catastrophic_false_accepts"] == 0,
        }
        gates[cohort] = {**checks, "all_pass": all(checks.values())}
    gates["both_cohorts_pass"] = gates["V4"]["all_pass"] and gates["V5"]["all_pass"]
    return gates


def main() -> dict[str, Any]:
    cohort_rows = {cohort: _load_rows(path) for cohort, path in QUEUE_PATHS.items()}
    scoped = scope_rows(cohort_rows)
    gallery, coverage_report = build_gallery_from_resolution(cohort_rows)

    per_row = {cohort: run_scoped_rows(cohort, rows, gallery) for cohort, rows in scoped.items()}
    reproduction = reproduction_check(per_row)
    coverage = exact_card_coverage(per_row)
    gates = four_gates(reproduction, coverage)

    output = {
        "label": NON_CERTIFYING_LABEL,
        "scoped_row_counts": {cohort: len(rows) for cohort, rows in scoped.items()},
        "total_scoped_rows": sum(len(rows) for rows in scoped.values()),
        "gallery_coverage": coverage_report,
        "reproduction_check": reproduction,
        "exact_card_coverage": coverage,
        "four_gates": gates,
        "note": "Measurement only. COMBINED-IDENTITY-v2 semantics/thresholds unchanged. "
                "Reused the exact frozen E2.8 execution path (build_gallery_from_resolution, "
                "classify_listing, resolve_image_state) -- no reimplementation.",
    }
    PER_ROW_OUTPUT_PATH.write_text(
        json.dumps(per_row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SUMMARY_OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2))
