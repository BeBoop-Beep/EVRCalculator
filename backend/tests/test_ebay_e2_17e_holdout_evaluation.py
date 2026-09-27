"""E2.17E integrity, metric, and research-policy regression tests."""
import csv
import json
import shutil

import pytest

from backend.scripts import run_ebay_e2_17e_holdout_evaluation as run
from backend.scripts import ebay_language_policy_v2 as lang
from backend.scripts import ebay_combined_identity_policy_v4 as combined
from backend.scripts import run_ebay_e2_17e_posthoc_diagnostics as posthoc
from backend.scripts.ebay_language_policy_v1 import LANGUAGE_MATCH, LANGUAGE_MISMATCH, LANGUAGE_UNVERIFIED


NEEDED = [
    "ebay_e2_17c_small_japanese_holdout_queue.csv",
    "ebay_e2_17c_small_japanese_holdout_raw_internal.jsonl",
    "ebay_e2_17c_small_japanese_holdout_review_history.jsonl",
    "ebay_e2_17c_small_japanese_holdout_manifest.json",
    "ebay_e2_17d_ocr_v3_holdout_predictions.json",
    "ebay_e2_17d_ocr_v3_freeze_manifest.json",
]


@pytest.fixture
def copied(tmp_path):
    for name in NEEDED:
        shutil.copy2(run.OUT / name, tmp_path / name)
    return tmp_path


@pytest.mark.parametrize("field,file_name", [
    ("corpus_fingerprint", "ebay_e2_17c_small_japanese_holdout_manifest.json"),
    ("label_fingerprint", "ebay_e2_17c_small_japanese_holdout_manifest.json"),
    ("freeze_fingerprint_sha256", "ebay_e2_17d_ocr_v3_freeze_manifest.json"),
    ("prediction_fingerprint_sha256", "ebay_e2_17d_ocr_v3_holdout_predictions.json"),
])
def test_fingerprint_mutation_blocks(copied, field, file_name):
    path = copied / file_name
    data = json.loads(path.read_text())
    data[field] = "0" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(run.PreconditionsFailed):
        run.preconditions(copied)


def test_row_set_mutation_blocks(copied):
    path = copied / "ebay_e2_17d_ocr_v3_holdout_predictions.json"
    data = json.loads(path.read_text())
    data["rows"][0]["row_id"] = "wrong"
    path.write_text(json.dumps(data))
    with pytest.raises(run.PreconditionsFailed):
        run.preconditions(copied)


def test_real_holdout_metrics_and_uncertain_exclusion():
    queue, pred, _ = run.preconditions()
    result = run.evaluate(queue, pred)
    assert result["confusion"] == {"TP": 4, "FP": 0, "FN": 2, "TN": 36}
    assert result["precision"] == 1
    assert result["japanese_recall"] == 4 / 6
    assert result["false_japanese_mismatch_rate"] == 0
    assert result["specificity"] == 1
    assert len(result["uncertain"]) == 1
    assert result["uncertain"][0]["row_id"] == "e2_17c_holdout_0007"


def test_all_confusion_quadrants_and_uncertain():
    labels = ["JAPANESE", "JAPANESE", "NOT_JAPANESE", "NOT_JAPANESE", "UNCERTAIN"]
    states = ["JAPANESE_MISMATCH", "UNVERIFIED", "JAPANESE_MISMATCH", "NOT_JAPANESE_EVIDENCE", "UNVERIFIED"]
    rows = [{"row_id": str(i), "canonical_card_id": str(i), "human_truth_label": label} for i, label in enumerate(labels)]
    preds = [{"row_id": str(i), "ocr_v3_decision": state} for i, state in enumerate(states)]
    result = run.evaluate(rows, preds)
    assert result["confusion"] == {"TP": 1, "FP": 1, "FN": 1, "TN": 1}
    assert result["precision"] == result["japanese_recall"] == 0.5
    assert result["false_japanese_mismatch_rate"] == 0.5
    assert result["specificity"] == 0.5
    assert len(result["uncertain"]) == 1


@pytest.mark.parametrize("provider,ocr,expected", [
    ("Korean", "UNVERIFIED", LANGUAGE_MISMATCH),
    ("Chinese", "UNVERIFIED", LANGUAGE_MISMATCH),
    ("Japanese", "UNVERIFIED", LANGUAGE_UNVERIFIED),
    ("English", "JAPANESE_MISMATCH", LANGUAGE_MISMATCH),
    ("Japanese", "JAPANESE_MISMATCH", LANGUAGE_MISMATCH),
    (None, "JAPANESE_MISMATCH", LANGUAGE_MISMATCH),
    ("French", "UNVERIFIED", LANGUAGE_UNVERIFIED),
    ("English", "UNVERIFIED", LANGUAGE_MATCH),
])
def test_language_v2_precedence(provider, ocr, expected):
    aspects = [{"name": "Language", "value": provider}] if provider else []
    assert lang.evaluate(aspects, ocr).language_state == expected


def test_combined_v4_rejects_language_only():
    mismatch = lang.evaluate([{"name": "Language", "value": "Korean"}])
    assert combined.combine("HIGH_CONFIDENCE", "MATCH", mismatch).combined_state == "REJECTED_LANGUAGE_CONTRADICTION"
    unverified = lang.evaluate([{"name": "Language", "value": "Japanese"}])
    assert combined.combine("HIGH_CONFIDENCE", "MATCH", unverified).is_eligible


def test_posthoc_is_non_certifying_and_missing_inputs_remain_unknown():
    result = posthoc.diagnostic()
    assert result["classification"] == "HISTORICAL_POST_HOC_NON_CERTIFYING"
    assert result["e214_key_row"]["ocr_v3_state"] is None
    assert result["e214_v4"] is None
    assert result["new_blind_capture_justified"] is False


def test_new_policies_do_not_write_production_data():
    import inspect
    for module in (lang, combined):
        source = inspect.getsource(module)
        assert "INSERT INTO" not in source
        assert "UPDATE prices" not in source
        assert "requests." not in source
