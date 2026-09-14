import hashlib
import json
from pathlib import Path

from backend.scripts.ebay_d3_matcher_v3 import MATCHER_VERSION, rule_fingerprint

OUT=Path(__file__).resolve().parents[3]/"artifacts/index_fair_value"


def artifact(name):
    return json.loads((OUT/name).read_text(encoding="utf-8"))


def test_full_development_manifest_is_complete_and_not_independent():
    found=artifact("ebay_d3_v3_development_manifest.json")
    assert (found["total_rows"],found["exact_count"],found["definitive_negative_count"],found["ambiguous_count"])==(1050,668,353,29)
    assert found["binary_denominator"]==1021 and found["independent_certification_evidence"] is False


def test_v3_development_metrics_preserve_all_non_image_only_high_protections():
    found=artifact("ebay_d3_v3_development_metrics.json")
    assert (found["high"]["accepted"],found["high"]["tp"],found["high"]["fp"])==(450,449,1)
    assert found["high"]["false_positive_breakdown"]=={"GRADED":1}
    assert found["high"]["false_positive_rows"][0]["benchmark_row_id"]=="D2-0310"
    assert all(value==0 for key,value in found["catastrophic_high_counts"].items() if key!="GRADED")


def test_failure_analyses_cover_known_rows_and_structured_fields():
    graded=artifact("ebay_d3_v3_graded_detection_analysis.json")
    multiple=artifact("ebay_d3_v3_multiplicity_analysis.json")
    assert "D2-0310" in graded["residual_high_image_only_risk_rows"]
    assert multiple["v3_multi_card_detected"]==multiple["human_multi_card_rows"]==26
    assert multiple["v3_high_false_positives"]==0 and "D2-0674" in multiple["d2_0674_finding"]


def test_power_and_design_are_preregistered_and_internally_fingerprinted():
    power=artifact("ebay_d3_new_certification_power_analysis.json")
    design=artifact("ebay_d3_new_blind_benchmark_design.json")
    assert power["minimum_high_n_with_zero_false_positives"]==189
    assert power["minimum_high_n_with_one_false_positive"]==280
    assert power["wilson_lower_at_299_of_300"]>.98
    fingerprint=design.pop("benchmark_design_fingerprint")
    expected=hashlib.sha256(json.dumps(design,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    assert fingerprint==expected
    assert design["api_plan"]["exact_maximum_browse_calls"]==140


def test_freeze_matches_committed_matcher_and_design():
    freeze=artifact("ebay_d3_v3_freeze_manifest.json")
    design=artifact("ebay_d3_new_blind_benchmark_design.json")
    assert freeze["matcher_version"]==MATCHER_VERSION
    assert freeze["matcher_fingerprint"]==rule_fingerprint()
    assert freeze["frozen_commit"]=="f744ae4b59e6d9efa02de08a23e07c68ac7c370c"
    assert freeze["benchmark_design_fingerprint"]==design["benchmark_design_fingerprint"]
    assert freeze["new_certification_labels_viewed"] is False
