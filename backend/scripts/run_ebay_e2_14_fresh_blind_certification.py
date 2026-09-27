"""EBAY_E2_14 Phase 2 -- EVALUATE. Joins the already-written, already-
fingerprinted Phase-1 prediction artifact to the final frozen human labels
by row_id. Never re-scores, never alters a prediction after reading labels.

UNCERTAIN rows are excluded from definitive precision/recall/false-accept
calculations (per instruction) but reported separately, never coerced to
YES or NO.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from backend.scripts.ebay_gold_access import OUT
from backend.scripts.ebay_e2_13_blind_review_server import load_queue_rows

PREDICTIONS_PATH = OUT / "ebay_e2_14_fresh_blind_predictions.json"
CERTIFICATION_OUTPUT_PATH = OUT / "ebay_e2_14_fresh_blind_certification.json"
E2_13_MANIFEST_PATH = OUT / "ebay_e2_13_fresh_blind_manifest.json"
COMBINED_V2_FREEZE_PATH = OUT / "ebay_combined_identity_v2_freeze_manifest.json"
ALLOCATION_V2_FREEZE_PATH = OUT / "ebay_capture_allocation_v2_freeze_manifest.json"
CANONICAL_MANIFEST_PATH = OUT / "ebay_image_v2_canonical_resolution_manifest.json"
POKEMON_COHORT_PATH = OUT / "ebay_pilot_cohort.json"

TOTAL_TARGET_CARDS = 70
DESIGN_GATE = {
    "accepted_precision_minimum": 0.99,
    "wilson_95_lower_minimum": 0.98,
    "card_coverage_minimum": 0.80,
    "catastrophic_false_accepts_maximum": 0,
}


def wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    if not total:
        return [0.0, 0.0]
    p = successes / total
    d = 1 + z * z / total
    c = (p + z * z / (2 * total)) / d
    m = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return [c - m, c + m]


def ratio(a: int, b: int) -> float:
    return a / b if b else 0.0


def run_precondition_checks() -> dict[str, Any]:
    from backend.scripts import ebay_d3_matcher_v5 as v5
    from backend.scripts import ebay_image_retrieval_verifier as image_v2
    from backend.scripts import ebay_combined_identity_policy_v2 as policy_v2
    from backend.scripts.freeze_ebay_capture_allocation_v2 import policy_fingerprint
    from backend.scripts.ebay_e2_13_blind_review_server import (
        load_queue_rows as _load, cohort_fingerprint as _cf,
        get_active_session_id, is_session_invalidated, CORRECTION_HISTORY_PATH,
        read_history, _history_fingerprint, assert_no_forbidden_columns,
    )
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import compute_label_fingerprint

    rows = _load()
    m = json.loads(E2_13_MANIFEST_PATH.read_text(encoding="utf-8"))
    frozen = json.loads(COMBINED_V2_FREEZE_PATH.read_text(encoding="utf-8"))
    alloc_frozen = json.loads(ALLOCATION_V2_FREEZE_PATH.read_text(encoding="utf-8"))
    canon_fp = hashlib.sha256(CANONICAL_MANIFEST_PATH.read_bytes()).hexdigest()
    corr_events = read_history(CORRECTION_HISTORY_PATH, actions=frozenset({"correction", "undo_correction"}))
    recomputed_alloc_fp = policy_fingerprint({k: v for k, v in alloc_frozen.items() if k != "allocation_fingerprint"})

    checks = {
        "row_count_553": len(rows) == 553,
        "target_universe_70": m.get("coverage_universe") == 70,
        "represented_cards_70": m.get("cards_represented") == 70,
        "cohort_fingerprint_matches": _cf(rows) == m["cohort_fingerprint"],
        "final_human_freeze_exists": m.get("finally_frozen") is True,
        "final_label_fingerprint_recomputes": compute_label_fingerprint(rows) == m["final_label_fingerprint"],
        "correction_history_fingerprint_matches": _history_fingerprint(corr_events) == m["correction_audit"]["correction_history_fingerprint"],
        "labels_complete": m.get("labels_exist") is True,
        "review_session_is_e2_13_session_1": get_active_session_id() == "e2_13_session_1",
        "session_not_invalidated": not is_session_invalidated(get_active_session_id()),
        "d3_v5_fingerprint_matches_frozen": v5.rule_fingerprint() == frozen["text_matcher_fingerprint"],
        "image_v2_fingerprint_matches_frozen": image_v2.source_sha256() == frozen["image_verifier_fingerprint"],
        "combined_v2_fingerprint_matches_frozen": policy_v2.policy_source_hash() == frozen["policy_source_sha256"],
        "allocation_v2_fingerprint_matches_frozen": recomputed_alloc_fp == alloc_frozen["allocation_fingerprint"] == m["capture_allocation_fingerprint"],
        "canonical_resolution_fingerprint_matches": canon_fp == m["canonical_resolution_manifest_fingerprint"],
        "capture_after_allocation_freeze": m["capture_finished_at"] > alloc_frozen["frozen_at"],
        "no_forbidden_columns_in_queue": True,
        "no_post_freeze_label_mutation": True,  # implied by final_label_fingerprint_recomputes above
    }
    try:
        assert_no_forbidden_columns(rows)
    except Exception:
        checks["no_forbidden_columns_in_queue"] = False

    # E2.9B and all prior evidence excluded -- verified directly (zero overlap)
    import csv
    new_ids = {r["listing_item_id"] for r in rows}
    prior_overlap = 0
    for prior_file in ("ebay_e2_9b_fresh_blind_queue.csv", "ebay_d3_v4_fresh_blind_queue.csv", "ebay_d3_v5_fresh_blind_queue.csv"):
        prior_path = OUT / prior_file
        if prior_path.exists():
            prior_ids = {r["listing_item_id"] for r in csv.DictReader(open(prior_path, encoding="utf-8"))}
            prior_overlap += len(new_ids & prior_ids)
    checks["prior_evidence_excluded_zero_overlap"] = prior_overlap == 0

    return checks


def _classify_no_reason(row: dict[str, Any]) -> str:
    if row.get("raw_or_graded") == "GRADED":
        return "GRADED"
    if row.get("single_card_or_lot") == "LOT_OR_BUNDLE":
        return "LOT_OR_BUNDLE"
    if row.get("card_or_sealed_nonshcard") == "SEALED_OR_NON_CARD":
        return "SEALED_OR_NON_CARD"
    if row.get("collector_number_consistency") == "INCONSISTENT":
        return "WRONG_CARD_NUMBER"
    if row.get("set_consistency") == "INCONSISTENT":
        return "WRONG_SET"
    if row.get("variant_treatment") == "INCONSISTENT":
        return "WRONG_VARIANT_OR_TREATMENT"
    if row.get("language") == "NON_ENGLISH":
        return "WRONG_LANGUAGE"
    return "WRONG_CARD_OR_OTHER"


def main() -> dict[str, Any]:
    precondition_results = run_precondition_checks()
    failed = [k for k, v in precondition_results.items() if not v]
    if failed:
        blocked = {
            "label": "EBAY_E2_14_CERTIFICATION_BLOCKED",
            "final_decision": f"EBAY_E2_14_CERTIFICATION_BLOCKED_{failed[0].upper()}",
            "precondition_results": precondition_results,
            "failed_preconditions": failed,
        }
        CERTIFICATION_OUTPUT_PATH.write_text(json.dumps(blocked, indent=2) + "\n", encoding="utf-8")
        return blocked

    predictions_doc = json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))
    predictions = predictions_doc["predictions"]
    recomputed_pred_fp = hashlib.sha256(
        json.dumps(predictions, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if recomputed_pred_fp != predictions_doc["predictions_fingerprint"]:
        blocked = {"final_decision": "EBAY_E2_14_CERTIFICATION_BLOCKED_PREDICTIONS_FINGERPRINT_MISMATCH"}
        CERTIFICATION_OUTPUT_PATH.write_text(json.dumps(blocked, indent=2) + "\n", encoding="utf-8")
        return blocked

    rows_by_id = {r["benchmark_row_id"]: r for r in load_queue_rows()}
    cohort = json.loads(POKEMON_COHORT_PATH.read_text(encoding="utf-8"))
    all_70_card_ids = {c["canonical_card_id"] for c in cohort["cards"]}
    represented_card_ids = {r["canonical_card_id"] for r in rows_by_id.values()}

    tier_a_true = tier_a_false = 0
    tier_b_true = tier_b_false = 0
    total_true = total_false = total_true_reject = total_false_reject = 0
    tier_a_cards: set[str] = set()
    false_accept_rows: list[dict[str, Any]] = []
    uncertain_count = uncertain_accepted = uncertain_rejected = 0

    for row_id, pred in predictions.items():
        row = rows_by_id[row_id]
        human = row["exact_match_yes_no_uncertain"]
        card_id = pred["canonical_card_id"]
        eligible = pred["eligible"]
        tier = pred["identity_tier"]

        if human == "UNCERTAIN":
            uncertain_count += 1
            if eligible:
                uncertain_accepted += 1
            else:
                uncertain_rejected += 1
            continue  # excluded from definitive metrics, never coerced

        if eligible:
            is_correct = human == "YES"
            if tier == "TIER_A":
                if is_correct:
                    tier_a_true += 1
                    tier_a_cards.add(card_id)
                else:
                    tier_a_false += 1
            elif tier == "TIER_B":
                if is_correct:
                    tier_b_true += 1
                else:
                    tier_b_false += 1
            if is_correct:
                total_true += 1
            else:
                total_false += 1
                classified_reason = _classify_no_reason(row)
                false_accept_rows.append({
                    "row_id": row_id, "canonical_card_id": card_id,
                    "target_card_name": row["target_card_name"], "target_set_name": row["target_set_name"],
                    "target_card_number": row["target_card_number"],
                    "listing_title": row["listing_title"],
                    "human_no_derived_reason": classified_reason,
                    "d3_v5_text_state": pred["text_state"], "image_v2_state": pred["image_state"],
                    "combined_v2_tier": tier, "combined_v2_state": pred["combined_state"],
                    "canonical_resolution_identity": card_id,
                })
        else:
            if human == "NO":
                total_true_reject += 1
            else:
                total_false_reject += 1

    tier_b_true_cards_all = {
        pred["canonical_card_id"] for row_id, pred in predictions.items()
        if pred["identity_tier"] == "TIER_B" and rows_by_id[row_id]["exact_match_yes_no_uncertain"] == "YES"
    }
    tier_b_only_cards = tier_b_true_cards_all - tier_a_cards
    all_covered_cards = tier_a_cards | tier_b_true_cards_all
    all_uncovered_cards = sorted(all_70_card_ids - all_covered_cards)

    total_accepted = tier_a_true + tier_a_false + tier_b_true + tier_b_false
    total_rejected = total_true_reject + total_false_reject
    total_definitive = total_accepted + total_rejected
    combined_true = tier_a_true + tier_b_true
    combined_false = tier_a_false + tier_b_false

    accepted_precision = ratio(combined_true, total_accepted)
    wilson_lower, wilson_upper = wilson(combined_true, total_accepted)
    recall = ratio(combined_true, sum(1 for r in rows_by_id.values() if r["exact_match_yes_no_uncertain"] == "YES"))
    row_acceptance_rate = ratio(total_accepted, total_definitive)
    card_coverage = len(all_covered_cards) / TOTAL_TARGET_CARDS

    metrics = {
        "definitive_row_count": total_definitive,
        "accepted_count": total_accepted, "true_accepts": combined_true, "false_accepts": combined_false,
        "rejected_count": total_rejected, "true_rejects": total_true_reject, "false_rejects": total_false_reject,
        "accepted_precision": accepted_precision,
        "accepted_precision_wilson_95": [wilson_lower, wilson_upper],
        "recall": recall, "row_acceptance_rate": row_acceptance_rate,
        "distinct_card_coverage": card_coverage,
    }
    uncertain_metrics = {
        "uncertain_count": uncertain_count, "uncertain_accepted": uncertain_accepted,
        "uncertain_rejected": uncertain_rejected,
    }
    tier_a_metrics = {
        "accepted_count": tier_a_true + tier_a_false, "true_accepts": tier_a_true, "false_accepts": tier_a_false,
        "precision": ratio(tier_a_true, tier_a_true + tier_a_false), "distinct_cards_covered": len(tier_a_cards),
    }
    tier_b_metrics = {
        "accepted_count": tier_b_true + tier_b_false, "true_accepts": tier_b_true, "false_accepts": tier_b_false,
        "precision": ratio(tier_b_true, tier_b_true + tier_b_false),
        "distinct_cards_covered": len(tier_b_true_cards_all),
        "distinct_cards_incrementally_recovered": len(tier_b_only_cards),
        "note": "Tier B is TEXT_VERIFIED_IMAGE_UNVERIFIED -- never image-verified.",
    }

    gates = {
        "accepted_precision_ge_0_99": accepted_precision >= DESIGN_GATE["accepted_precision_minimum"],
        "wilson_lower_ge_0_98": wilson_lower >= DESIGN_GATE["wilson_95_lower_minimum"],
        "card_coverage_ge_0_80_denominator_70": card_coverage >= DESIGN_GATE["card_coverage_minimum"],
        "catastrophic_false_accepts_eq_0": len(false_accept_rows) == 0,
    }
    all_pass = all(gates.values())
    if all_pass:
        final_decision = "EBAY_COMBINED_IDENTITY_V2_ALLOCATION_V2_FRESH_BLIND_CERTIFIED"
    else:
        failed_gates = [k for k, v in gates.items() if not v]
        final_decision = f"EBAY_COMBINED_IDENTITY_V2_ALLOCATION_V2_FRESH_BLIND_NOT_CERTIFIED_{failed_gates[0].upper()}"

    e213_manifest = json.loads(E2_13_MANIFEST_PATH.read_text(encoding="utf-8"))
    output = {
        "label": "EBAY_E2_14_ALLOCATION_V2_FRESH_BLIND_CERTIFICATION",
        "final_decision": final_decision,
        "production_authority": False,
        "precondition_results": precondition_results,
        "predictions_fingerprint": predictions_doc["predictions_fingerprint"],
        "human_label_fingerprint": e213_manifest["final_label_fingerprint"],
        "correction_history_fingerprint": e213_manifest["correction_audit"]["correction_history_fingerprint"],
        "canonical_resolution_fingerprint": hashlib.sha256(CANONICAL_MANIFEST_PATH.read_bytes()).hexdigest(),
        "capture_allocation_v2_fingerprint": e213_manifest["capture_allocation_fingerprint"],
        "coverage_universe": TOTAL_TARGET_CARDS,
        "metrics": metrics,
        "uncertain": uncertain_metrics,
        "tier_a": tier_a_metrics,
        "tier_b": tier_b_metrics,
        "card_coverage_detail": {
            "tier_a_covered_card_ids": sorted(tier_a_cards),
            "tier_b_only_incremental_card_ids": sorted(tier_b_only_cards),
            "all_covered_card_ids": sorted(all_covered_cards),
            "all_uncovered_card_ids": all_uncovered_cards,
            "covered_count": len(all_covered_cards), "denominator": TOTAL_TARGET_CARDS,
        },
        "false_accept_rows": false_accept_rows,
        "false_accept_taxonomy_counts": {
            k: sum(1 for r in false_accept_rows if r["human_no_derived_reason"] == k)
            for k in ("WRONG_CARD", "WRONG_CARD_NUMBER", "WRONG_SET", "WRONG_VARIANT_OR_TREATMENT",
                      "GRADED", "LOT_OR_BUNDLE", "SEALED_OR_NON_CARD", "WRONG_LANGUAGE", "OTHER", "WRONG_CARD_OR_OTHER")
        },
        "gates": gates,
    }
    CERTIFICATION_OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    result = main()
    print(json.dumps({k: v for k, v in result.items() if k != "false_accept_rows"}, indent=2))
