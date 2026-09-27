"""E2.18A authority and E13-0127 non-certifying decisive-gate tests."""
import hashlib
import json
from pathlib import Path

import pytest

from backend.scripts import ebay_e2_17d_ocr_v3_hangul_recalibration as ocr
from backend.scripts import ebay_language_policy_v2 as language
from backend.scripts import run_ebay_e2_18_e13_0127_decisive_diagnostic as diagnostic


def test_image_source_exact_frozen_bytes():
    diagnostic.verify_authority()
    path = Path("backend/scripts/ebay_image_retrieval_verifier.py")
    manifest = json.loads((diagnostic.OUT / "ebay_image_retrieval_verifier_v2_freeze_manifest.json").read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["verifier_source_sha256"]
    assert b"\r\n" not in path.read_bytes()


def test_frozen_image_mismatch_blocks(monkeypatch):
    monkeypatch.setattr(diagnostic.image_v2, "source_sha256", lambda: "0" * 64)
    with pytest.raises(RuntimeError, match="FROZEN_AUTHORITY_MISMATCH_IMAGE_V2"):
        diagnostic.verify_authority()


def test_missing_getitem_and_image_are_unverified():
    assert language.evaluate([], "UNVERIFIED").language_state == "LANGUAGE_UNVERIFIED"
    evidence = ocr.run_ocr_v3(None, None, "definitely_missing_image.jpg", "missing")
    assert ocr.ocr_v3_decision(evidence)[0] == "UNVERIFIED"


@pytest.mark.parametrize("value,expected", [
    ("Korean", "LANGUAGE_MISMATCH"),
    ("Chinese", "LANGUAGE_MISMATCH"),
    ("Japanese", "LANGUAGE_UNVERIFIED"),
])
def test_provider_precedence(value, expected):
    assert language.evaluate([{"name": "Language", "value": value}], "UNVERIFIED").language_state == expected


def test_ocr_japanese_mismatch_vetoes():
    assert language.evaluate([], "JAPANESE_MISMATCH").language_state == "LANGUAGE_MISMATCH"


def test_e13_prediction_sealed_before_truth_and_still_false_accept():
    artifact = json.loads((diagnostic.OUT / "ebay_e2_18_e13_0127_combined_v4_prediction.json").read_text())
    row = artifact["row"]
    assert "human_truth" not in row
    assert diagnostic.sha256_bytes(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()) == artifact["prediction_fingerprint_sha256"]
    result = json.loads((diagnostic.OUT / "ebay_e2_18_e13_0127_decisive_diagnostic.json").read_text())
    assert result["row_id"] == "E13-0127"
    assert result["human_truth"] == "NO"
    assert result["false_accept"] is True
    assert result["mandatory_e13_rejection_gate_passed"] is False
