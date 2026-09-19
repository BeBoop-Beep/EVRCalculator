"""EBAY_E2_9C Phase 1 -- SCORE the frozen combined-identity stack against the
already-captured, already-finally-frozen E2.9B fresh blind cohort.

CERTIFYING (once joined to human labels in Phase 2 -- this script performs
Phase 1 ONLY: prediction, no evaluation). Calls D3-v5, IMAGE-v2, and
COMBINED-IDENTITY-v2 exactly as frozen; imports no new logic of its own
beyond wiring. The scoring function below (`score_row`) takes only fields a
human reviewer's raw listing data would supply -- it has no access to, and
never reads, `exact_match_yes_no_uncertain` or any other human-label column
from the queue. Phase separation is structural: this script's output
(the prediction artifact) is written and fingerprinted BEFORE any label is
consulted; Phase 2 (a separate script) reads this frozen artifact back and
joins it to labels afterward -- this script cannot alter its own output in
response to labels because it never sees them.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts.ebay_combined_identity_policy_v1 import (
    has_text_contradiction,
    resolve_image_state,
)
from backend.scripts import ebay_combined_identity_policy_v2 as policy_v2
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.ebay_image_retrieval_verifier import CanonicalGallery
from backend.scripts.ebay_e2_9b_blind_review_server import load_queue_rows, QUEUE_PATH

CANONICAL_MANIFEST_PATH = OUT / "ebay_image_v2_canonical_resolution_manifest.json"
PREDICTIONS_OUTPUT_PATH = OUT / "ebay_combined_identity_v2_fresh_blind_predictions.json"


def _target_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_name": row["target_card_name"], "set_name": row["target_set_name"],
        "card_number": row["target_card_number"], "treatment": row["target_treatment"],
        "canonical_card_id": row["canonical_card_id"],
    }


def _listing_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": row["listing_title"], "condition": row["condition"], "conditionId": row["condition_id"],
        "category": row.get("category_id") or "", "aspects": "[]",
        "buying_options": row.get("buying_options_json") or "[]", "itemId": row["listing_item_id"],
    }


def build_gallery() -> CanonicalGallery:
    """Loads the DURABLE canonical-resolution manifest E2.9B preserved
    (byte-identical to the original E2.8 scratch manifest) -- does NOT
    resolve or fetch any new canonical target, per instruction."""
    resolved = json.loads(CANONICAL_MANIFEST_PATH.read_text(encoding="utf-8"))
    gallery = CanonicalGallery()
    added: set[str] = set()
    for entry in resolved.values():
        cid = entry["canonical_card_id"]
        if cid in added or not entry.get("found") or not entry.get("image_path"):
            continue
        image_path = Path(entry["image_path"])
        if not image_path.exists():
            continue
        gallery.add(
            canonical_card_id=cid, canonical_image_url=entry.get("image_url", ""),
            image_bytes=image_path.read_bytes(), card_name=entry.get("name", ""),
        )
        added.add(cid)
    return gallery


def score_row(row: dict[str, Any], gallery: CanonicalGallery) -> dict[str, Any]:
    """Scores ONE listing using only listing/target fields -- never reads
    `row["exact_match_yes_no_uncertain"]` or any other human-label column.
    """
    text_result = v5.classify_listing(_target_dict(row), _listing_dict(row))
    text_state = text_result["identity_state"]
    contradiction = has_text_contradiction(row)

    image_result = resolve_image_state(gallery, row["canonical_card_id"], row.get("image_url", ""))
    image_state = image_result["image_identity_state"]

    combined = policy_v2.combine(text_state, image_state, text_row_fields=row)

    return {
        "row_id": row["benchmark_row_id"],
        "canonical_card_id": row["canonical_card_id"],
        "listing_item_id": row["listing_item_id"],
        "text_state": text_state,
        "text_contradiction_present": contradiction,
        "image_state": image_state,
        "image_verification_reason": image_result.get("verification_reason", ""),
        "image_diagnostic": {
            k: image_result.get(k) for k in (
                "target_rank", "target_similarity", "top1_card_id", "top1_similarity",
                "top2_similarity", "target_vs_top1_gap", "top1_vs_top2_margin",
                "card_region_detected", "canonical_image_available", "listing_image_available",
            ) if k in image_result
        },
        "combined_state": combined.combined_state,
        "identity_tier": (
            "TIER_A" if combined.combined_state == policy_v2.TIER_A_IMAGE_VERIFIED else
            "TIER_B" if combined.combined_state == policy_v2.TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED else
            "NOT_ELIGIBLE"
        ),
        "eligible": combined.is_eligible,
        "reason": combined.reason,
    }


def main() -> dict[str, Any]:
    rows = load_queue_rows()
    gallery = build_gallery()
    predictions = {}
    for row in rows:
        # Structural guarantee scoring never touches the label: pass a copy
        # with the label field stripped, so a future edit to score_row
        # cannot silently start reading it.
        row_no_label = dict(row)
        row_no_label.pop("exact_match_yes_no_uncertain", None)
        predictions[row["benchmark_row_id"]] = score_row(row_no_label, gallery)

    predictions_fingerprint = hashlib.sha256(
        json.dumps(predictions, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    output = {
        "label": "EBAY_COMBINED_IDENTITY_V2_FRESH_BLIND_PREDICTIONS",
        "phase": "PHASE_1_SCORE_LABEL_BLIND",
        "source_queue_path": str(QUEUE_PATH),
        "row_count": len(predictions),
        "predictions": predictions,
        "predictions_fingerprint": predictions_fingerprint,
        "scoring_note": (
            "score_row() never reads exact_match_yes_no_uncertain or any "
            "other human-label column; the row dict passed to it has that "
            "field removed before scoring, structurally, not just by "
            "convention."
        ),
    }
    PREDICTIONS_OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    result = main()
    print(json.dumps({k: v for k, v in result.items() if k != "predictions"}, indent=2))
