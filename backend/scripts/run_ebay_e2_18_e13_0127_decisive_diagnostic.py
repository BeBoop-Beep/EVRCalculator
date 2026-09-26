"""Seal a non-certifying E13-0127 policy prediction before reading human truth.

This targeted diagnostic is sufficient to test the mandatory known-row gate.
It does not claim whole-cohort E2.14 metrics.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.scripts import ebay_combined_identity_policy_v4 as combined_v4
from backend.scripts import ebay_language_policy_v2 as language_v2
from backend.scripts import ebay_image_retrieval_verifier as image_v2

OUT = Path(__file__).resolve().parents[1] / "artifacts/index_fair_value"
ROW_ID = "E13-0127"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_authority(out: Path = OUT) -> None:
    image_manifest = json.loads((out / "ebay_image_retrieval_verifier_v2_freeze_manifest.json").read_text(encoding="utf-8"))
    if image_v2.source_sha256() != image_manifest["verifier_source_sha256"]:
        raise RuntimeError("EBAY_E2_18_BLOCKED_FROZEN_AUTHORITY_MISMATCH_IMAGE_V2")
    for module, filename in ((language_v2, "ebay_e2_17e_language_v2_freeze_manifest.json"),
                             (combined_v4, "ebay_e2_17e_combined_identity_v4_freeze_manifest.json")):
        manifest = json.loads((out / filename).read_text(encoding="utf-8"))
        if module.policy_source_hash() != manifest["source_sha256"]:
            raise RuntimeError("EBAY_E2_18_BLOCKED_FROZEN_AUTHORITY_MISMATCH_" + module.METHOD_VERSION)


def seal_prediction(out: Path = OUT) -> dict:
    verify_authority(out)
    provider_path = out / "ebay_e2_18_e13_0127_getitem_probe.json"
    ocr_path = out / "ebay_e2_18_e13_0127_ocr_v3_probe.json"
    provider = json.loads(provider_path.read_text(encoding="utf-8"))
    ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
    frozen = json.loads((out / "ebay_e2_14_fresh_blind_predictions.json").read_text(encoding="utf-8"))["predictions"][ROW_ID]
    if provider["row_id"] != ocr["row_id"] or provider["row_id"] != ROW_ID:
        raise RuntimeError("row binding mismatch")
    if provider["listing_item_id"] != ocr["listing_item_id"] or provider["fetch_status"] != 200:
        raise RuntimeError("provider evidence unavailable or misbound")
    if ocr["image_fetch_status"] != 200 or not ocr["evidence"]["ocr_ok"]:
        raise RuntimeError("OCR evidence unavailable")
    language = language_v2.evaluate(provider["localizedAspects"], ocr["ocr_v3_state"])
    # This frozen row has no D3-v5 text contradiction. The baseline prediction
    # carries that machine fact, so no human-review queue is opened here.
    if frozen["text_contradiction_present"]:
        raise RuntimeError("unexpected text contradiction in known row")
    combined = combined_v4.combine(frozen["text_state"], frozen["image_state"], language, {})
    row = {
        "row_id": ROW_ID,
        "listing_item_id": provider["listing_item_id"],
        "provider_language_raw": provider["raw_language_value"],
        "provider_language_normalized": language.observed_language,
        "provider_fetch_status": provider["fetch_status"],
        "ocr_v3_state": ocr["ocr_v3_state"],
        "ocr_v3_reason": ocr["reason_code"],
        "image_fetch_status": ocr["image_fetch_status"],
        "text_state": frozen["text_state"],
        "image_state": frozen["image_state"],
        "language_v2_state": language.language_state,
        "combined_v4_state": combined.combined_state,
        "eligible": combined.is_eligible,
    }
    fingerprint = sha256_bytes(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    artifact = {"classification": "HISTORICAL_POST_HOC_NON_CERTIFYING",
                "scope": "E13-0127 decisive gate only", "row": row,
                "prediction_fingerprint_sha256": fingerprint,
                "provider_artifact_sha256": sha256_bytes(provider_path.read_bytes()),
                "ocr_artifact_sha256": sha256_bytes(ocr_path.read_bytes())}
    (out / "ebay_e2_18_e13_0127_combined_v4_prediction.json").write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return artifact


def evaluate_sealed_prediction(out: Path = OUT) -> dict:
    import csv
    artifact = json.loads((out / "ebay_e2_18_e13_0127_combined_v4_prediction.json").read_text(encoding="utf-8"))
    row = artifact["row"]
    recomputed = sha256_bytes(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    if recomputed != artifact["prediction_fingerprint_sha256"]:
        raise RuntimeError("prediction fingerprint mismatch")
    with (out / "ebay_e2_13_fresh_blind_queue.csv").open(encoding="utf-8", newline="") as handle:
        truth = next(r for r in csv.DictReader(handle) if r["benchmark_row_id"] == ROW_ID)
    result = {"classification": "HISTORICAL_POST_HOC_NON_CERTIFYING", "row_id": ROW_ID,
              "human_truth": truth["exact_match_yes_no_uncertain"],
              "eligible": row["eligible"], "combined_v4_state": row["combined_v4_state"],
              "false_accept": truth["exact_match_yes_no_uncertain"] == "NO" and row["eligible"],
              "mandatory_e13_rejection_gate_passed": not row["eligible"]}
    (out / "ebay_e2_18_e13_0127_decisive_diagnostic.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(seal_prediction()["row"], indent=2))
    print(json.dumps(evaluate_sealed_prediction(), indent=2))
