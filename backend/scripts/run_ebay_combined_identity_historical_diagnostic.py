"""EBAY_E2_8 historical post-hoc diagnostic for COMBINED-IDENTITY-v1.

NON-CERTIFYING (HISTORICAL_POST_HOC_NON_CERTIFYING). Runs the FIXED,
already-frozen combination of D3-v5 (text) and IMAGE-v2 (image, frozen
research candidate) against the two CONSUMED blind cohorts (V4: 420 rows,
V5: 417 rows) purely as after-the-fact diagnostic evidence for whether a
new fresh-blind certification round is justified.

This script is explicitly NOT a tuning tool:
  - D3-v5 is called exactly as frozen (classify_listing()) -- untouched.
  - IMAGE-v2's thresholds are imported, never redefined here.
  - COMBINED-IDENTITY-v1's decision table (ebay_combined_identity_policy_v1)
    is the fixed table written for this task, not fit to this data.
Running this script and reading its output must never be followed by
editing any threshold in any of the three layers on the basis of what it
shows.

Per-row canonical images for gallery-coverage purposes are resolved
JUST-IN-TIME from the public Pokemon TCG API (the same free/local-cost
canonical-image authority IMAGE-v2 already uses) rather than assuming the
static 165-card IMAGE-v2 research gallery already contains all 140 unique
V4/V5 target cards -- it does not, by construction (that gallery was built
from 26 unrelated Pokemon-name families for E2.7's research, not from
inDex's actual benchmark target population). Rows whose target could not be
resolved are honestly reported as gallery-coverage gaps
(UNVERIFIED_TARGET_NOT_IN_GALLERY), never silently skipped.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts.ebay_combined_identity_policy_v1 import (
    IMAGE_UNVERIFIED_TARGET_NOT_IN_GALLERY,
    REJECTED_IMAGE_CONTRADICTION,
    REJECTED_TEXT,
    TEXT_AMBIGUOUS_NOT_PROMOTED,
    TEXT_MATCH_IMAGE_UNVERIFIED,
    VERIFIED_MATCH,
    combine,
    resolve_image_state,
)
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.ebay_image_retrieval_verifier import CanonicalGallery

QUEUE_PATHS = {
    "V4": OUT / "ebay_d3_v4_fresh_blind_queue.csv",
    "V5": OUT / "ebay_d3_v5_fresh_blind_queue.csv",
}
RESOLVE_MANIFEST_PATH = Path(
    r"C:\Users\Owner\AppData\Local\Temp\claude\d--EVRCalculator\ab525fb1-3a68-4190-b321-235965717bad\scratchpad\e28_canonical_targets\resolve_manifest.json"
)
DIAGNOSTIC_OUTPUT_PATH = OUT / "ebay_combined_identity_v1_historical_post_hoc_diagnostic.json"

NON_CERTIFYING_LABEL = "HISTORICAL_POST_HOC_NON_CERTIFYING"

DESIGN_GATE = {
    "high_precision_minimum": 0.99, "wilson_95_lower_minimum": 0.98,
    "card_coverage_minimum": 0.80, "catastrophic_high_false_positives_maximum": 0,
}


def _load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _target_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {"card_name": row["target_card_name"], "set_name": row["target_set_name"],
            "card_number": row["target_card_number"], "treatment": row["target_treatment"],
            "canonical_card_id": row["canonical_card_id"]}


def _listing_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {"title": row["listing_title"], "condition": row["condition"], "conditionId": row["condition_id"],
            "category": row.get("category_id") or "", "aspects": "[]",
            "buying_options": row.get("buying_options_json") or "[]", "itemId": row["listing_item_id"]}


def classify_human_label(row: dict[str, Any]) -> str:
    value = str(row.get("exact_match_yes_no_uncertain", "")).strip().lower()
    if value == "yes":
        return "yes"
    if value == "no":
        return "no"
    return "uncertain"


def build_gallery_from_resolution(cohort_rows: dict[str, list[dict[str, Any]]]) -> tuple[CanonicalGallery, dict[str, Any]]:
    resolved = json.loads(RESOLVE_MANIFEST_PATH.read_text(encoding="utf-8")) if RESOLVE_MANIFEST_PATH.exists() else {}
    gallery = CanonicalGallery()
    added = set()
    requested_ids: set[str] = set()
    present_ids: set[str] = set()
    missing_ids: set[str] = set()

    for cohort, rows in cohort_rows.items():
        for row in rows:
            requested_ids.add(row["canonical_card_id"])

    for key, entry in resolved.items():
        cid = entry["canonical_card_id"]
        if cid in added:
            continue
        if entry.get("found") and entry.get("image_path") and Path(entry["image_path"]).exists():
            gallery.add(
                canonical_card_id=cid, canonical_image_url=entry.get("image_url", ""),
                image_bytes=Path(entry["image_path"]).read_bytes(), card_name=entry.get("name", ""),
            )
            added.add(cid)
            present_ids.add(cid)
        else:
            missing_ids.add(cid)

    missing_ids -= present_ids
    coverage_report = {
        "requested_target_count": len(requested_ids),
        "target_identities_present_in_gallery": len(present_ids & requested_ids),
        "missing_target_identities": sorted(requested_ids - present_ids),
        "visual_coverage_percentage": round(100.0 * len(present_ids & requested_ids) / len(requested_ids), 2) if requested_ids else 0.0,
    }
    return gallery, coverage_report


def wilson(successes: int, total: int) -> list[float]:
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


def run_cohort(cohort: str, rows: list[dict[str, Any]], gallery: CanonicalGallery) -> dict[str, Any]:
    definitive_rows = [r for r in rows if classify_human_label(r) in ("yes", "no")]
    uncertain_count = sum(1 for r in rows if classify_human_label(r) == "uncertain")

    failure_matrix: Counter = Counter()
    combined_state_counts: Counter = Counter()
    accepted = tp = fp = 0
    catastrophic_combined_errors = []
    cards_with_true_accept: set[str] = set()
    all_cards = {r["canonical_card_id"] for r in rows}

    for row in definitive_rows:
        text_result = v5.classify_listing(_target_dict(row), _listing_dict(row))
        text_state = text_result["identity_state"]
        image_state_result = resolve_image_state(gallery, row["canonical_card_id"], row.get("image_url", ""))
        image_state = image_state_result["image_identity_state"]
        combined = combine(text_state, image_state, text_row_fields=row)

        human = "YES" if classify_human_label(row) == "yes" else "NO"
        failure_matrix[(text_state, image_state, human, combined.combined_state)] += 1
        combined_state_counts[combined.combined_state] += 1

        card_id = row["canonical_card_id"]
        if combined.combined_state == VERIFIED_MATCH:
            accepted += 1
            if human == "YES":
                tp += 1
                cards_with_true_accept.add(card_id)
            else:
                fp += 1
                catastrophic_combined_errors.append({
                    "benchmark_row_id": row["benchmark_row_id"], "cohort": cohort,
                    "text_state": text_state, "image_state": image_state, "human_label": human,
                })

    positives_total = sum(1 for r in definitive_rows if classify_human_label(r) == "yes")
    metrics = {
        "total_rows": len(rows), "definitive_rows": len(definitive_rows), "uncertain_rows": uncertain_count,
        "combined_state_counts": dict(combined_state_counts),
        "accepted_count": accepted, "true_accepts": tp, "false_accepts": fp,
        "accepted_precision": ratio(tp, accepted), "accepted_precision_wilson_95": wilson(tp, accepted),
        "accepted_recall": ratio(tp, positives_total),
        "cards_with_true_accept": len(cards_with_true_accept), "cards_total": len(all_cards),
        "card_coverage": ratio(len(cards_with_true_accept), len(all_cards)),
        "catastrophic_combined_false_accepts": catastrophic_combined_errors,
        "catastrophic_combined_false_accept_count": len(catastrophic_combined_errors),
    }
    gates = {
        "accepted_precision": {"status": "PASS" if accepted and metrics["accepted_precision"] >= DESIGN_GATE["high_precision_minimum"] else ("NOT_EVALUABLE" if not accepted else "FAIL"), "observed": metrics["accepted_precision"]},
        "wilson_lower": {"status": "PASS" if accepted and metrics["accepted_precision_wilson_95"][0] >= DESIGN_GATE["wilson_95_lower_minimum"] else ("NOT_EVALUABLE" if not accepted else "FAIL"), "observed": metrics["accepted_precision_wilson_95"][0]},
        "coverage": {"status": "PASS" if metrics["card_coverage"] >= DESIGN_GATE["card_coverage_minimum"] else "FAIL", "observed": metrics["card_coverage"]},
        "catastrophic": {"status": "PASS" if fp == 0 else "FAIL", "observed": fp},
    }
    return {"metrics": metrics, "diagnostic_gates": gates, "failure_matrix": [
        {"text_state": k[0], "image_state": k[1], "human_label": k[2], "combined_state": k[3], "count": v}
        for k, v in sorted(failure_matrix.items(), key=lambda kv: -kv[1])
    ]}


def main() -> dict[str, Any]:
    cohort_rows = {cohort: _load_rows(path) for cohort, path in QUEUE_PATHS.items()}
    gallery, coverage_report = build_gallery_from_resolution(cohort_rows)

    results = {cohort: run_cohort(cohort, rows, gallery) for cohort, rows in cohort_rows.items()}

    output = {
        "label": NON_CERTIFYING_LABEL,
        "gallery_coverage": coverage_report,
        "results": results,
        "note": "Historical post-hoc diagnostic only. Never certifies COMBINED-IDENTITY-v1, D3-v5, or IMAGE-v2, "
                "and must never be used to re-tune any threshold in any layer.",
    }
    DIAGNOSTIC_OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    output = main()
    print(json.dumps({k: v for k, v in output.items() if k != "results"}, indent=2))
    for cohort, result in output["results"].items():
        print(cohort, json.dumps(result["metrics"], indent=2)[:2000])
