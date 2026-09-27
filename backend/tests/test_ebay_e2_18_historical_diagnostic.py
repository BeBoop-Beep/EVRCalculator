"""Focused checks for bounded E2.18 reconstruction and sealed diagnostics."""
import hashlib
import json

import pytest

from backend.scripts import run_ebay_e2_18_reconstruct_evidence as reconstruction
from backend.scripts import run_ebay_e2_18_combined_v4_diagnostic as diagnostic
from backend.scripts import ebay_language_policy_v2 as language


def test_frozen_authority_gate_and_mismatch(monkeypatch):
    diagnostic.verify_authority()
    monkeypatch.setattr(diagnostic.image_v2, "source_sha256", lambda: "0" * 64)
    with pytest.raises(RuntimeError, match="MISMATCH_IMAGE_V2"):
        diagnostic.verify_authority()


def test_missing_provider_and_ocr_preserve_unverified():
    assert language.evaluate(None, "UNVERIFIED").language_state == "LANGUAGE_UNVERIFIED"
    assert reconstruction.MAX_TASK_GETITEM_REQUESTS == 200


def test_evidence_inputs_are_label_blind():
    for cohort in reconstruction.QUEUE:
        rows = reconstruction.inputs(cohort)
        assert len(rows) > 0
        assert set(rows[0]) == {"row_id", "listing_item_id", "image_url"}
        machine = diagnostic.machine_rows(cohort)
        assert "exact_match_yes_no_uncertain" not in machine[0]
        assert "language" not in machine[0]


@pytest.mark.parametrize("cohort", ["E2.14", "V4", "V5"])
def test_sealed_predictions_before_truth_join(cohort):
    path = diagnostic.OUT / f"ebay_e2_18_{cohort.lower().replace('.', '_')}_combined_v4_predictions.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    rows = artifact["predictions"]
    assert len(rows) == artifact["row_count"]
    assert len({r["row_id"] for r in rows}) == len(rows)
    assert all("human_truth" not in r and "exact_match_yes_no_uncertain" not in r for r in rows)
    fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert fingerprint == artifact["prediction_fingerprint_sha256"]


def test_e214_decisive_diagnostic_and_coverage_denominator():
    result = json.loads((diagnostic.OUT / "ebay_e2_18_e2_14_combined_v4_diagnostic.json").read_text())
    assert result["classification"] == diagnostic.CLASSIFICATION
    assert result["card_coverage_denominator"] == 70
    assert result["card_coverage_count"] == 58
    assert result["false_accepts"] == result["catastrophic_false_accept_count"] == 1
    assert result["catastrophic_false_accept_rows"] == ["E13-0127"]
    assert result["precision_wilson_95"][0] < 0.98


def test_wilson_and_no_new_accepts():
    from backend.scripts.run_ebay_combined_identity_v3_prospective_diagnostic import wilson
    assert wilson(258, 259)[0] < 0.98
    for cohort in ("E2.14", "V4", "V5"):
        path = diagnostic.OUT / f"ebay_e2_18_{cohort.lower().replace('.', '_')}_combined_v4_diagnostic.json"
        result = json.loads(path.read_text())
        assert result["newly_accepted_rows"] == []
