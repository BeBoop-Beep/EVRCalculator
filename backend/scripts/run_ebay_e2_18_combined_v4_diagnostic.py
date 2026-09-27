"""Seal label-blind historical COMBINED-v4 predictions, then evaluate them.

All results are HISTORICAL_POST_HOC_NON_CERTIFYING. Missing evidence is
explicitly UNVERIFIED; it is never inferred from human labels or titles.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from backend.scripts import ebay_combined_identity_policy_v2 as combined_v2
from backend.scripts import ebay_combined_identity_policy_v4 as combined_v4
from backend.scripts import ebay_language_policy_v2 as language_v2
from backend.scripts import ebay_d3_matcher_v5 as d3
from backend.scripts import ebay_image_retrieval_verifier as image_v2
from backend.scripts.run_ebay_combined_identity_historical_diagnostic import (
    _target_dict, _listing_dict, build_gallery_from_resolution,
)
from backend.scripts.ebay_combined_identity_policy_v1 import resolve_image_state, TEXT_CONTRADICTION_FIELDS
from backend.scripts.run_ebay_combined_identity_v3_prospective_diagnostic import wilson
from backend.scripts.run_ebay_e2_18_reconstruct_evidence import OUT, QUEUE, artifact_path, read_existing

CLASSIFICATION = "HISTORICAL_POST_HOC_NON_CERTIFYING"
FROZEN_PREDICTIONS = {
    "E2.14": "ebay_e2_14_fresh_blind_predictions.json",
    "E2.9B": "ebay_combined_identity_v2_fresh_blind_predictions.json",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_authority() -> None:
    from backend.scripts import ebay_e2_17d_ocr_v3_hangul_recalibration as ocr
    from backend.scripts import freeze_ebay_capture_allocation_v2 as allocation
    image_manifest = json.loads((OUT / "ebay_image_retrieval_verifier_v2_freeze_manifest.json").read_text())
    ocr_manifest = json.loads((OUT / "ebay_e2_17d_ocr_v3_freeze_manifest.json").read_text())
    lang_manifest = json.loads((OUT / "ebay_e2_17e_language_v2_freeze_manifest.json").read_text())
    combined_manifest = json.loads((OUT / "ebay_e2_17e_combined_identity_v4_freeze_manifest.json").read_text())
    base_manifest = json.loads((OUT / "ebay_combined_identity_v2_freeze_manifest.json").read_text())
    canon = sha((OUT / "ebay_image_v2_canonical_resolution_manifest.json").read_bytes())
    e214 = json.loads((OUT / "ebay_e2_14_fresh_blind_certification.json").read_text())
    allocation_manifest = json.loads((OUT / "ebay_capture_allocation_v2_freeze_manifest.json").read_text())
    allocation_current = allocation.build_manifest()
    allocation_ok = all(allocation_manifest[key] == allocation_current[key] for key in (
        "query_generation_fingerprint", "sampling_source_fingerprint",
        "historical_exclusion_source_fingerprint")) and allocation.policy_fingerprint({
            key: value for key, value in allocation_manifest.items() if key != "allocation_fingerprint"
        }) == allocation_manifest["allocation_fingerprint"]
    checks = {
        "IMAGE_V2": image_v2.source_sha256() == image_manifest["verifier_source_sha256"],
        "OCR_V3": ocr.compute_source_fingerprint() == ocr_manifest["source_fingerprint_sha256"],
        "LANGUAGE_V2": language_v2.policy_source_hash() == lang_manifest["source_sha256"],
        "COMBINED_V4": combined_v4.policy_source_hash() == combined_manifest["source_sha256"],
        "D3_V5": d3.rule_fingerprint() == base_manifest["text_matcher_fingerprint"],
        "CANONICAL_RESOLUTION": canon == e214["canonical_resolution_fingerprint"],
        "CAPTURE_ALLOCATION_V2": allocation_ok,
    }
    for authority, okay in checks.items():
        if not okay:
            raise RuntimeError("EBAY_E2_18_BLOCKED_FROZEN_AUTHORITY_MISMATCH_" + authority)


def machine_rows(cohort: str) -> list[dict[str, str]]:
    required = ("benchmark_row_id", "listing_item_id", "image_url", "canonical_card_id",
                "target_card_name", "target_set_name", "target_card_number", "target_treatment",
                "listing_title", "condition", "condition_id", "category_id", "buying_options_json")
    with (OUT / QUEUE[cohort]).open(encoding="utf-8", newline="") as handle:
        return [{k: row.get(k, "") for k in required} for row in csv.DictReader(handle)]


def base_predictions(cohort: str, rows: list[dict[str, str]]) -> dict[str, dict]:
    if cohort in FROZEN_PREDICTIONS:
        saved = json.loads((OUT / FROZEN_PREDICTIONS[cohort]).read_text())["predictions"]
        if set(saved) != {r["benchmark_row_id"] for r in rows}:
            raise RuntimeError("frozen baseline row membership mismatch")
        return saved
    # Historical V4/V5 have no frozen per-row image predictions. Recompute
    # their D3-v5 and IMAGE-v2 states under exact frozen source authorities.
    all_rows = {c: machine_rows(c) for c in ("V4", "V5")}
    gallery, _ = build_gallery_from_resolution(all_rows)
    result = {}
    for i, row in enumerate(rows, 1):
        text = d3.classify_listing(_target_dict(row), _listing_dict(row))["identity_state"]
        image = resolve_image_state(gallery, row["canonical_card_id"], row["image_url"])["image_identity_state"]
        baseline = combined_v2.combine(text, image, text_row_fields={})
        result[row["benchmark_row_id"]] = {"text_state": text, "image_state": image,
                                           "text_contradiction_present": baseline.text_contradiction_present,
                                           "eligible": baseline.is_eligible}
        if i % 25 == 0:
            print(cohort, "base", i, "/", len(rows), flush=True)
    return result


def seal(cohort: str) -> dict:
    verify_authority()
    rows = machine_rows(cohort)
    provider = read_existing(artifact_path(cohort, "provider"))
    ocr = read_existing(artifact_path(cohort, "ocr_v3"))
    if set(provider) - {r["benchmark_row_id"] for r in rows} or set(ocr) - {r["benchmark_row_id"] for r in rows}:
        raise RuntimeError("evidence row outside cohort")
    base = base_predictions(cohort, rows)
    predictions = []
    for row in rows:
        row_id = row["benchmark_row_id"]
        prior = base[row_id]
        p = provider.get(row_id)
        o = ocr.get(row_id)
        if p and p["listing_item_id"] != row["listing_item_id"]:
            raise RuntimeError("provider item binding mismatch")
        if o and (o["listing_item_id"] != row["listing_item_id"] or o["image_url"] != row["image_url"]):
            raise RuntimeError("OCR item/image binding mismatch")
        p_ok = bool(p and p["fetch_status"] == 200)
        o_ok = bool(o and o["image_fetch_status"] == 200 and o["evidence"]["ocr_ok"])
        aspects = p["localizedAspects"] if p_ok else None
        ocr_state = o["ocr_v3_state"] if o_ok else "UNVERIFIED"
        language = language_v2.evaluate(aspects, ocr_state)
        # Frozen baseline contradiction is a machine prediction, not truth.
        text_fields = {TEXT_CONTRADICTION_FIELDS[0]: "inconsistent"} if prior.get("text_contradiction_present") else {}
        combined = combined_v4.combine(prior["text_state"], prior["image_state"], language, text_fields)
        predictions.append({"row_id": row_id, "listing_item_id": row["listing_item_id"],
                            "canonical_card_id": row["canonical_card_id"],
                            "text_state": prior["text_state"], "image_state": prior["image_state"],
                            "provider_fetch_status": p["fetch_status"] if p else "NOT_ATTEMPTED_BUDGET",
                            "provider_language_raw": p["raw_language_value"] if p_ok else None,
                            "provider_language_normalized": language.observed_language,
                            "ocr_image_fetch_status": o["image_fetch_status"] if o else "NOT_ATTEMPTED",
                            "ocr_v3_state": ocr_state, "ocr_v3_reason": o["reason_code"] if o else "EVIDENCE_UNAVAILABLE",
                            "language_v2_state": language.language_state,
                            "combined_v4_state": combined.combined_state,
                            "eligible": combined.is_eligible, "baseline_eligible": bool(prior["eligible"]),
                            "provider_evidence_available": p_ok and p["raw_language_value"] is not None,
                            "ocr_evidence_available": o_ok})
    fingerprint = sha(json.dumps(predictions, sort_keys=True, separators=(",", ":")).encode())
    artifact = {"classification": CLASSIFICATION, "cohort": cohort, "row_count": len(predictions),
                "prediction_fingerprint_sha256": fingerprint, "predictions": predictions,
                "authority": "frozen D3-v5/IMAGE-v2/OCR-v3/LANGUAGE-v2/COMBINED-v4"}
    output = OUT / f"ebay_e2_18_{cohort.lower().replace('.', '_')}_combined_v4_predictions.json"
    output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return artifact


def evaluate(cohort: str) -> dict:
    path = OUT / f"ebay_e2_18_{cohort.lower().replace('.', '_')}_combined_v4_predictions.json"
    sealed = json.loads(path.read_text(encoding="utf-8"))
    predictions = sealed["predictions"]
    if sha(json.dumps(predictions, sort_keys=True, separators=(",", ":")).encode()) != sealed["prediction_fingerprint_sha256"]:
        raise RuntimeError("prediction fingerprint mismatch")
    with (OUT / QUEUE[cohort]).open(encoding="utf-8", newline="") as handle:
        truth = {r["benchmark_row_id"]: r for r in csv.DictReader(handle)}
    if set(truth) != {r["row_id"] for r in predictions}:
        raise RuntimeError("truth/prediction row membership mismatch")
    accepted = true_accepts = false_accepts = 0
    cards = set()
    false_rows = []
    newly_rejected_yes = []
    newly_accepted = []
    for pred in predictions:
        human = truth[pred["row_id"]]["exact_match_yes_no_uncertain"]
        if pred["eligible"] and not pred["baseline_eligible"]:
            newly_accepted.append(pred["row_id"])
        if human == "YES" and pred["baseline_eligible"] and not pred["eligible"]:
            newly_rejected_yes.append(pred["row_id"])
        if human not in ("YES", "NO"):
            continue
        if pred["eligible"]:
            accepted += 1
            if human == "YES":
                true_accepts += 1
                cards.add(pred["canonical_card_id"])
            else:
                false_accepts += 1
                false_rows.append(pred["row_id"])
    availability = Counter()
    for pred in predictions:
        p, o = pred["provider_evidence_available"], pred["ocr_evidence_available"]
        availability["both" if p and o else "provider_only" if p else "ocr_only" if o else "neither"] += 1
    result = {"classification": CLASSIFICATION, "cohort": cohort,
              "prediction_fingerprint_sha256": sealed["prediction_fingerprint_sha256"],
              "rows_total": len(predictions), "evidence_availability": dict(availability),
              "language_unverified_count": sum(r["language_v2_state"] == "LANGUAGE_UNVERIFIED" for r in predictions),
              "accepted_count": accepted, "true_accepts": true_accepts, "false_accepts": false_accepts,
              "precision": true_accepts / accepted if accepted else None,
              "precision_wilson_95": wilson(true_accepts, accepted),
              "card_coverage_count": len(cards), "card_coverage_denominator": 70,
              "card_coverage": len(cards) / 70,
              "catastrophic_false_accept_count": len(false_rows), "catastrophic_false_accept_rows": false_rows,
              "newly_rejected_human_yes_rows": newly_rejected_yes,
              "newly_accepted_rows": newly_accepted}
    (OUT / f"ebay_e2_18_{cohort.lower().replace('.', '_')}_combined_v4_diagnostic.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", choices=list(QUEUE), required=True)
    args = parser.parse_args()
    saved = seal(args.cohort)
    print("sealed", args.cohort, saved["row_count"], saved["prediction_fingerprint_sha256"], flush=True)
    print(json.dumps(evaluate(args.cohort), indent=2))
