"""EBAY E2.15 Phase K -- read-only post-hoc COMBINED-IDENTITY-v3 diagnostic.

Runs LANGUAGE-v1 (structured-aspect only; see
backend/services/ebay_language_evidence_v1.py) against the ALREADY-FROZEN
E2.14 fresh-blind prediction + certification artifacts and reports what
COMBINED-IDENTITY-v3 (v2 + language-contradiction veto) WOULD have done.

This is explicitly NON-CERTIFYING:
  - E2.14 is a consumed, frozen cohort. Nothing here re-scores, re-labels,
    or re-runs E2.14 as a certification.
  - No new live language evidence is fetched for the E2.14 rows here
    (that would touch the consumed cohort). Coverage is reported honestly
    as "not evaluable from existing artifacts" for the WRONG_LANGUAGE row
    itself, because the frozen E2.14 prediction rows do not carry
    localizedAspects payloads -- only human review labels and identity
    verdicts. This script does NOT invent a language aspect for that row.

Output is written to a diagnostics-only path and is read-only with respect
to production tables, publish paths, and the frozen E2.14 artifacts
themselves (they are opened for reading only).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.scripts.index_fair_value_ebay_evidence_collector import ROOT

ARTIFACTS_DIR = ROOT / "backend/artifacts/index_fair_value"
E214_PRED_PATH = ARTIFACTS_DIR / "ebay_e2_14_fresh_blind_predictions.json"
E214_CERT_PATH = ARTIFACTS_DIR / "ebay_e2_14_fresh_blind_certification.json"
OUT_PATH = ARTIFACTS_DIR / "ebay_e2_15_combined_v3_posthoc_diagnostic.json"


def main() -> None:
    preds = json.loads(E214_PRED_PATH.read_text(encoding="utf-8"))
    cert = json.loads(E214_CERT_PATH.read_text(encoding="utf-8"))

    metrics = cert["metrics"]
    taxonomy = cert["false_accept_taxonomy_counts"]

    result: dict[str, Any] = {
        "diagnostic": "ebay_e2_15_phase_k_combined_v3_posthoc",
        "certifying": False,
        "read_only": True,
        "e214_source_fingerprint": {
            "predictions_path": str(E214_PRED_PATH),
            "certification_path": str(E214_CERT_PATH),
            "row_count": preds.get("row_count"),
        },
        "note": (
            "LANGUAGE-v1 is structured-aspect-only in this environment "
            "(no OCR path was built -- see E2.15 report Phase F). The "
            "frozen E2.14 prediction rows do not carry localizedAspects "
            "payloads, so LANGUAGE-v1 cannot be mechanically evaluated "
            "against the 1 WRONG_LANGUAGE catastrophic row or any other "
            "E2.14 row from the existing artifacts alone. This diagnostic "
            "therefore reports the E2.14 baseline numbers only, plus the "
            "SIZING-ONLY hypothetical of what COMBINED-IDENTITY-v3 would "
            "achieve IF the veto perfectly caught that one row and no "
            "true accept, sourced directly from "
            "false_accept_taxonomy_counts.WRONG_LANGUAGE in the frozen "
            "certification artifact (already 1, already isolated from "
            "other false-accept classes) -- this is not a re-run or "
            "re-score of E2.14, only arithmetic over its frozen output."
        ),
        "e214_baseline": {
            "accepted_count": metrics["accepted_count"],
            "true_accepts": metrics["true_accepts"],
            "false_accepts": metrics["false_accepts"],
            "accepted_precision": metrics["accepted_precision"],
            "wrong_language_false_accepts": taxonomy.get("WRONG_LANGUAGE", 0),
            "card_coverage": cert["card_coverage_detail"],
        },
        "combined_v3_sizing_only_hypothetical": None,
        "wired_into_production": False,
    }

    wrong_language_count = taxonomy.get("WRONG_LANGUAGE", 0)
    if wrong_language_count:
        accepted2 = metrics["accepted_count"] - wrong_language_count
        true_a2 = metrics["true_accepts"]
        result["combined_v3_sizing_only_hypothetical"] = {
            "assumption": (
                "LANGUAGE-v1/COMBINED-v3 rejects exactly the "
                f"{wrong_language_count} WRONG_LANGUAGE false-accept row(s) "
                "and zero true accepts -- NOT VERIFIED against real "
                "evidence for this cohort, sizing-only, non-certifying."
            ),
            "accepted_count": accepted2,
            "true_accepts": true_a2,
            "false_accepts": metrics["false_accepts"] - wrong_language_count,
            "precision": (true_a2 / accepted2) if accepted2 else None,
            "catastrophic_false_accepts": 0,
        }

    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
