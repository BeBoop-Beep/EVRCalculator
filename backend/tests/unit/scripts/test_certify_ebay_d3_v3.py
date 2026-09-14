import csv
import hashlib
import json
from pathlib import Path

from backend.scripts.certify_ebay_d3_v3 import (
    coverage_metrics,
    high_precision_metrics,
    wilson,
)


ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "backend/artifacts/index_fair_value"


def row(card,gold,state):return {"canonical_card_id":card,"target_card_name":card,"human_gold":gold,"matcher_state":state}


def test_precision_uses_all_high_rows_and_ambiguous_is_false_positive():
 rows=[row("a","EXACT_TARGET_MATCH","HIGH_CONFIDENCE"),row("b","AMBIGUOUS","HIGH_CONFIDENCE"),row("c","GRADED","HIGH_CONFIDENCE")]
 found=high_precision_metrics(rows)
 assert found["evaluable_rows"]==3 and found["human_ambiguous_rows"]==1
 assert (found["true_positives"],found["false_positives"],found["precision"])==(1,2,0.33333333)
 assert found["false_positives_by_human_label"]=={"AMBIGUOUS":1,"GRADED":1}


def test_wilson_matches_preregistered_power_case():
 assert wilson(299,300)==[0.98136331,0.99941134]


def test_coverage_uses_fixed_card_denominator_and_medium_does_not_count():
 rows=[]
 for card in range(70):
  rows.extend([row(str(card),"EXACT_TARGET_MATCH","HIGH_CONFIDENCE" if card<56 else "MEDIUM_CONFIDENCE")]+[row(str(card),"GRADED","REJECTED") for _ in range(5)])
 found=coverage_metrics(rows)
 assert found["logical_rows"]==420 and found["all_cards_have_six"] is True
 assert found["covered_cards"]==56 and found["card_coverage"]==.8
 assert found["false_negatives"]==14 and found["medium_count"]==14


def test_frozen_certification_artifacts_reproduce_final_failure():
    metrics_path = OUT / "ebay_d3_v3_final_certification_metrics.json"
    manifest_path = OUT / "ebay_d3_v3_final_certification_manifest.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    with (OUT / "ebay_d3_v3_precision_certification_rows.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        precision_rows = list(csv.DictReader(handle))
    with (OUT / "ebay_d3_v3_coverage_certification_rows.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        coverage_rows = list(csv.DictReader(handle))
    with (OUT / "ebay_d3_v3_high_false_positive_forensics.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        forensic_rows = list(csv.DictReader(handle))

    precision_items = {row["listing_item_id"] for row in precision_rows}
    coverage_items = {row["listing_item_id"] for row in coverage_rows}
    assert (len(precision_rows), len(coverage_rows)) == (300, 420)
    assert len(precision_items & coverage_items) == 16
    assert len(precision_items | coverage_items) == 704

    precision = metrics["precision_cohort"]
    assert (precision["evaluable_rows"], precision["true_positives"], precision["false_positives"]) == (300, 297, 3)
    assert precision["precision"] == 0.99
    assert precision["wilson_95"] == [0.97101651, 0.99659338]

    coverage = metrics["coverage_cohort"]
    assert (coverage["logical_rows"], coverage["high_count"]) == (420, 207)
    assert (coverage["high_true_positives"], coverage["high_false_positives"]) == (205, 2)
    assert coverage["recall"] == 0.82995951
    assert (coverage["covered_cards"], coverage["card_coverage"]) == (55, 0.78571429)
    assert len(coverage["cards_with_zero_valid_high_exact"]) == 15

    assert metrics["catastrophic_high_errors"] == {
        "GRADED": 0,
        "LOT_OR_BUNDLE": 2,
        "SEALED_OR_ACCESSORY": 1,
        "WRONG_CARD_NUMBER": 2,
        "RELATED_BUT_WRONG_VARIANT": 0,
        "WRONG_SET": 0,
        "WRONG_LANGUAGE": 0,
        "AMBIGUOUS": 0,
    }
    assert len(forensic_rows) == 5
    assert metrics["medium_diagnostics"] == {
        "unique_row_count": 15,
        "exact_matches": 12,
        "false_positives": 3,
        "precision": 0.8,
        "incremental_coverage_cards": 5,
        "authority": "DIAGNOSTIC_ONLY",
    }
    assert metrics["gates"] == {
        "precision": True,
        "wilson_lower": False,
        "coverage": False,
        "catastrophic": False,
    }
    assert metrics["overall_result"] == "FAIL"

    assert manifest["certification_metrics_fingerprint"] == hashlib.sha256(
        metrics_path.read_bytes()
    ).hexdigest()
    stored_manifest_hash = manifest.pop("manifest_fingerprint")
    reproduced_manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert stored_manifest_hash == reproduced_manifest_hash
    assert manifest["final_result"] == "EBAY_IDENTITY_MATCHER_V3_NOT_VALIDATED"
