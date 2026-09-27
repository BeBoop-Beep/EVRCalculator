"""EBAY_E2_11 Phase I -- PROSPECTIVE, NON-CERTIFYING diagnostic combining
candidate TEXT D3-v6 + unchanged IMAGE-v2 + unchanged COMBINED-IDENTITY-v2
policy semantics ("COMBINED-IDENTITY-v3" only in the sense of a prospective
future stack label -- this is NOT a new policy module, NOT a certification,
and must never be described as one).

Reuses the already-frozen Phase-1 image-state predictions from E2.9C's
scoring run (IMAGE-v2 is unchanged, so its per-row output is unchanged) and
only re-derives the TEXT layer using candidate D3-v6, then re-applies the
unchanged combine() from ebay_combined_identity_policy_v2. Runs against V4,
V5, and the consumed E2.9B cohort as post-hoc, non-certifying diagnostics.
"""
from __future__ import annotations

import csv
import json
import math
from typing import Any

from backend.scripts import ebay_d3_matcher_v6 as v6
from backend.scripts import ebay_combined_identity_policy_v1 as policy_v1
from backend.scripts import ebay_combined_identity_policy_v2 as policy_v2
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.run_ebay_combined_identity_historical_diagnostic import (
    QUEUE_PATHS as HISTORICAL_QUEUE_PATHS, _target_dict, _listing_dict,
    build_gallery_from_resolution, classify_human_label,
)

E2_9B_QUEUE_PATH = OUT / "ebay_e2_9b_fresh_blind_queue.csv"
E2_9C_PREDICTIONS_PATH = OUT / "ebay_combined_identity_v2_fresh_blind_predictions.json"
OUTPUT_PATH = OUT / "ebay_combined_identity_v3_prospective_diagnostic.json"

TOTAL_TARGET_CARDS = 70


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


def diagnose_historical(cohort: str, gallery) -> dict[str, Any]:
    rows = list(csv.DictReader(open(HISTORICAL_QUEUE_PATHS[cohort], encoding="utf-8")))
    accepted = tp = fp = 0
    cards_true_accept: set[str] = set()
    all_cards = {r["canonical_card_id"] for r in rows}
    catastrophic = []
    for row in rows:
        human_label = classify_human_label(row)
        if human_label not in ("yes", "no"):
            continue
        text_result = v6.classify_listing(_target_dict(row), _listing_dict(row))
        text_state = text_result["identity_state"]
        image_result = policy_v1.resolve_image_state(gallery, row["canonical_card_id"], row.get("image_url", ""))
        image_state = image_result["image_identity_state"]
        combined = policy_v2.combine(text_state, image_state, text_row_fields=row)
        human = "YES" if human_label == "yes" else "NO"
        if combined.is_eligible:
            accepted += 1
            if human == "YES":
                tp += 1
                cards_true_accept.add(row["canonical_card_id"])
            else:
                fp += 1
                catastrophic.append({"row_id": row["benchmark_row_id"], "text_state": text_state,
                                      "image_state": image_state, "combined_state": combined.combined_state})
    return _package(cohort, accepted, tp, fp, len(cards_true_accept), catastrophic)


def diagnose_e2_9b(gallery) -> dict[str, Any]:
    predictions = json.loads(E2_9C_PREDICTIONS_PATH.read_text(encoding="utf-8"))["predictions"]
    rows = {r["benchmark_row_id"]: r for r in csv.DictReader(open(E2_9B_QUEUE_PATH, encoding="utf-8"))}
    accepted = tp = fp = 0
    cards_true_accept: set[str] = set()
    catastrophic = []
    for row_id, pred in predictions.items():
        row = rows[row_id]
        human = row["exact_match_yes_no_uncertain"]
        if human not in ("YES", "NO"):
            continue
        text_result = v6.classify_listing(_target_dict(row), _listing_dict(row))
        text_state = text_result["identity_state"]
        # IMAGE-v2 is unchanged -- reuse its already-frozen E2.9C output rather
        # than re-running real network+model inference for a diagnostic pass.
        image_state = pred["image_state"]
        combined = policy_v2.combine(text_state, image_state, text_row_fields=row)
        if combined.is_eligible:
            accepted += 1
            if human == "YES":
                tp += 1
                cards_true_accept.add(row["canonical_card_id"])
            else:
                fp += 1
                catastrophic.append({"row_id": row_id, "text_state": text_state,
                                      "image_state": image_state, "combined_state": combined.combined_state})
    return _package("E2.9B", accepted, tp, fp, len(cards_true_accept), catastrophic)


def _package(cohort, accepted, tp, fp, cards_covered, catastrophic) -> dict[str, Any]:
    wilson_lower, wilson_upper = wilson(tp, accepted)
    return {
        "cohort": cohort, "accepted_count": accepted, "true_accepts": tp, "false_accepts": fp,
        "accepted_precision": ratio(tp, accepted), "accepted_precision_wilson_95": [wilson_lower, wilson_upper],
        "card_coverage": cards_covered / TOTAL_TARGET_CARDS, "distinct_cards_covered": cards_covered,
        "catastrophic_false_accepts": catastrophic, "catastrophic_false_accept_count": len(catastrophic),
    }


def main() -> dict[str, Any]:
    cohort_rows = {c: list(csv.DictReader(open(p, encoding="utf-8"))) for c, p in HISTORICAL_QUEUE_PATHS.items()}
    gallery, _coverage = build_gallery_from_resolution(cohort_rows)

    results = {
        "V4": diagnose_historical("V4", gallery),
        "V5": diagnose_historical("V5", gallery),
        "E2.9B": diagnose_e2_9b(gallery),
    }
    gates = {}
    for cohort, m in results.items():
        gates[cohort] = {
            "precision_ge_0_99": m["accepted_precision"] >= 0.99,
            "wilson_lower_ge_0_98": m["accepted_precision_wilson_95"][0] >= 0.98,
            "coverage_ge_0_80": m["card_coverage"] >= 0.80,
            "catastrophic_eq_0": m["catastrophic_false_accept_count"] == 0,
        }

    output = {
        "label": "COMBINED_IDENTITY_V3_PROSPECTIVE_DIAGNOSTIC_NON_CERTIFYING",
        "note": "Prospective diagnostic only (D3-v6 + unchanged IMAGE-v2 + unchanged COMBINED-v2 policy). "
                "NOT a certification. E2.9B is consumed, post-hoc, non-certifying evidence here.",
        "text_matcher_version": v6.MATCHER_VERSION,
        "results": results,
        "gates": gates,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
