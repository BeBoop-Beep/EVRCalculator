"""EBAY_E2_14 Phase 1 -- SCORE the frozen combined-identity stack against the
already-captured, already-finally-frozen E2.13 fresh blind cohort (captured
under frozen CAPTURE-ALLOCATION-v2).

CERTIFYING (once joined to human labels in Phase 2 -- this script performs
Phase 1 ONLY: prediction, no evaluation). Calls D3-v5, IMAGE-v2, and
COMBINED-IDENTITY-v2 exactly as frozen. Reuses the exact scoring logic
already proven in E2.9C's scoring script
(run_ebay_combined_identity_v2_fresh_blind_scoring.py), retargeted at the
E2.13 queue -- the scoring function itself is unchanged; only the source
queue differs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from backend.scripts.run_ebay_combined_identity_v2_fresh_blind_scoring import build_gallery, score_row
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.ebay_e2_13_blind_review_server import load_queue_rows, QUEUE_PATH

PREDICTIONS_OUTPUT_PATH = OUT / "ebay_e2_14_fresh_blind_predictions.json"


def main() -> dict[str, Any]:
    rows = load_queue_rows()
    gallery = build_gallery()
    predictions = {}
    for row in rows:
        # Structural guarantee scoring never touches the label: pass a copy
        # with the label field stripped, so score_row cannot read it even
        # if a future edit tried to.
        row_no_label = dict(row)
        row_no_label.pop("exact_match_yes_no_uncertain", None)
        predictions[row["benchmark_row_id"]] = score_row(row_no_label, gallery)

    predictions_fingerprint = hashlib.sha256(
        json.dumps(predictions, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    output = {
        "label": "EBAY_E2_14_FRESH_BLIND_PREDICTIONS",
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
