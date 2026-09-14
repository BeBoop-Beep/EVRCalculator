import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[3] / "artifacts" / "index_fair_value"


def test_unlabeled_gold_set_forces_all_authorities_closed():
    rows = list(csv.DictReader((OUT / "ebay_manual_gold_labels.csv").open(encoding="utf-8")))
    assert len(rows) == 1050
    assert not any(row["gold_label"] for row in rows)
    decision = json.loads((OUT / "ebay_authority_acceptance.json").read_text(encoding="utf-8"))
    assert decision["activeSupply"].endswith("NOT_READY")
    assert decision["askingPrice"].endswith("NOT_READY")
    assert decision["fairValueSignal"].endswith("NOT_READY")
    assert decision["d3PersistentCollectorReady"] is False


def test_benchmarks_do_not_report_metrics_without_truth():
    for name in ("ebay_matcher_d1_benchmark.json", "ebay_matcher_d2_benchmark.json"):
        payload = json.loads((OUT / name).read_text(encoding="utf-8"))
        assert payload["precision"] is None
        assert payload["recall"] is None


def test_condition_authorities_are_separate():
    contract = json.loads((OUT / "ebay_condition_contract.json").read_text(encoding="utf-8"))
    assert "RAW_CONDITION_UNGRADED_UNSPECIFIED" in contract["supplyEligibility"]
    assert "RAW_CONDITION_UNGRADED_UNSPECIFIED" not in contract["askingPriceEligibility"]
