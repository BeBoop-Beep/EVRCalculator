"""Freeze research LANGUAGE-v2 and COMBINED-IDENTITY-v4 after holdout pass."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.scripts import ebay_language_policy_v2 as language
from backend.scripts import ebay_combined_identity_policy_v4 as combined
from backend.scripts import ebay_combined_identity_policy_v3 as prior

OUT = Path(__file__).resolve().parents[1] / "artifacts/index_fair_value"


def hash_material(material: dict) -> str:
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def freeze(out: Path = OUT) -> tuple[dict, dict]:
    evaluation_path = out / "ebay_e2_17e_ocr_v3_holdout_evaluation.json"
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    c = evaluation["confusion"]
    if c != {"TP": 4, "FP": 0, "FN": 2, "TN": 36} or any(
        r["ocr_v3_decision"] != "UNVERIFIED" for r in evaluation["japanese_misses"]
    ):
        raise RuntimeError("holdout gate did not pass")
    integrity = evaluation["integrity"]
    evaluation_fingerprint = hashlib.sha256(evaluation_path.read_bytes()).hexdigest()
    lang_material = {
        "version": language.METHOD_VERSION,
        "source_sha256": language.policy_source_hash(),
        "supported_provider_vocabulary": list(language.SUPPORTED_PROVIDER_VOCABULARY),
        "ocr_v3_freeze_fingerprint": integrity["ocr_v3_freeze_fingerprint"],
        "holdout_corpus_fingerprint": integrity["corpus_fingerprint"],
        "holdout_label_fingerprint": integrity["label_fingerprint"],
        "holdout_evaluation_fingerprint": evaluation_fingerprint,
        "production_authority": False,
    }
    lang = {**lang_material, "freeze_fingerprint_sha256": hash_material(lang_material)}
    combined_material = {
        "version": combined.METHOD_VERSION,
        "source_sha256": combined.policy_source_hash(),
        "prior_combined_v3_source_sha256": prior.policy_source_hash(),
        "language_v2_freeze_fingerprint": lang["freeze_fingerprint_sha256"],
        "semantics": "COMBINED-v3 unchanged except LANGUAGE-v2 input; mismatch rejects before eligibility",
        "production_authority": False,
    }
    comb = {**combined_material, "freeze_fingerprint_sha256": hash_material(combined_material)}
    (out / "ebay_e2_17e_language_v2_freeze_manifest.json").write_text(
        json.dumps(lang, indent=2) + "\n", encoding="utf-8")
    (out / "ebay_e2_17e_combined_identity_v4_freeze_manifest.json").write_text(
        json.dumps(comb, indent=2) + "\n", encoding="utf-8")
    return lang, comb


if __name__ == "__main__":
    print(json.dumps(freeze(), indent=2))
