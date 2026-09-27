import inspect
import json
from decimal import Decimal
from pathlib import Path

import pytest

from backend.benchmarking import publication_v1
from backend.domain.pokemon.rip_benchmark_v1 import (
    APPROVED_BENCHMARK_KEY, APPROVED_CALIBRATION_VERSION, APPROVED_MODEL_VERSIONS,
    APPROVED_SCALES, BenchmarkError, approved_calibrations, preview_score,
)


ARTIFACT = Path(__file__).parents[2] / "artifacts" / "rip_benchmark_v1" / "publisher_dry_run_2026-09-15.json"


def test_approved_calibration_registration_is_exactly_model_scoped():
    calibrations = approved_calibrations(APPROVED_MODEL_VERSIONS)
    assert set(calibrations) == {"financial", "chase", "collector", "overall"}
    assert {key: value.scale for key, value in calibrations.items()} == APPROVED_SCALES
    assert {value.version for value in calibrations.values()} == {APPROVED_CALIBRATION_VERSION}
    assert {value.benchmark_key for value in calibrations.values()} == {APPROVED_BENCHMARK_KEY}


@pytest.mark.parametrize("metric,wrong", [("financial", "financial_rip_v5"),
                                            ("overall", "overall_rip_v14"),
                                            ("collector", "collector_v7")])
def test_other_model_families_cannot_use_approved_calibration(metric, wrong):
    versions = dict(APPROVED_MODEL_VERSIONS); versions[metric] = wrong
    with pytest.raises(BenchmarkError, match="exact certified model family"):
        approved_calibrations(versions)


def test_every_approved_calibration_has_exact_five_anchor():
    for calibration in approved_calibrations(APPROVED_MODEL_VERSIONS).values():
        assert preview_score(Decimal("123.456"), Decimal("123.456"), calibration) == 5


def test_reviewed_22_set_references_ranges_and_db_candidate_contract():
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert artifact["status"] == "dry_run_validated_not_published"
    assert artifact["production_publish_enabled"] is True
    assert artifact["references"] == {
        "financial": "31.94342272727272727272727273",
        "chase": "47.66021818181818181818181818",
        "collector": "79.72324545454545454545454545",
        "overall": "37.35008181818181818181818182"}
    expected = {"financial": ("2.146215454545454545454545454", "7.034835454545454545454545454"),
        "chase": ("2.943588181818181818181818182", "7.608328181818181818181818182"),
        "collector": ("1.935135454545454545454545455", "6.937095454545454545454545455"),
        "overall": ("2.811083636363636363636363636", "6.771563636363636363636363636")}
    for metric, (low, high) in expected.items():
        item = artifact["score_distributions"][metric]
        assert (item["score_min"], item["score_max"]) == (low, high)
        assert item["clipped_at_0"] == item["clipped_at_10"] == item["monotonicity_violations"] == item["rank_inversions"] == 0
        assert item["score_at_exact_reference"] == "5"
    request = artifact["publish_rpc_request"]
    assert request["mode"] == "dry_run_only" and request["production_publish_enabled"] is False
    assert request["rpc"] == "publish_pokemon_rip_benchmark_v1"
    assert len(request["arguments"]["p_rows"]) == artifact["expected_row_count"] == 648
    assert request["arguments"]["p_header"]["expected_entity_count"] == 162


def test_product_inheritance_era_unavailability_and_global_reference_separation():
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert artifact["product_inheritance_counts"] == {"chase": 138, "collector": 138}
    assert artifact["era_unavailable_count"] == 0
    assert artifact["unavailable_counts"] == {}
    assert artifact["benchmark_unavailable_counts"] == {}
    rows = artifact["publish_rpc_request"]["arguments"]["p_rows"]
    native_products = [row for row in rows if row["entity_type"] == "sealed_product"
                       and row["metric_key"] in ("financial", "overall")]
    assert len(native_products) == 276
    assert all(row["benchmark_status"] == "available" for row in native_products)
    assert all(row["rank"] is None for row in native_products if row["metric_key"] == "financial")
    assert artifact["product_calibration_version"] == "rip_product_benchmark_v1_fin5_overall5_family_mean"
    global_return = str(artifact["opening_economics_reference"]["modeled_return_on_spend"])
    assert global_return not in set(artifact["references"].values())
    inherited = [row for row in artifact["publish_rpc_request"]["arguments"]["p_rows"]
                 if row["entity_type"] == "sealed_product" and row["metric_key"] in ("chase", "collector")]
    assert len(inherited) == 276 and all(row["rank"] is None for row in inherited)
    assert {k: v["member_count"] for k, v in artifact["product_family_policy"]["families"].items()} == {
        "booster_box": 15, "booster_bundle": 23, "elite_trainer_box": 27,
        "enhanced_booster_box": 2, "half_booster_box": 8, "loose_booster_pack": 22,
        "pokemon_center_elite_trainer_box": 26, "sleeved_booster_pack": 15}
    product_financial = [row for row in artifact["publish_rpc_request"]["arguments"]["p_rows"]
                         if row["entity_type"] == "sealed_product" and row["metric_key"] == "financial"]
    assert len(product_financial) == 138 and all(row["rank"] is None for row in product_financial)
    assert {c["scale"] for c in artifact["product_calibration_study"]["metrics"]["financial"]["candidates"]} >= {"5"}


def test_sep15_sep14_evidence_condition_is_reproduced_and_not_guessed():
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    forensic = artifact["product_financial_evidence_date_forensics"]
    assert forensic["model_market_dates"] == ["2026-09-15"]
    assert forensic["product_price_as_of_dates"] == ["2026-09-14"]
    assert forensic["affected_product_count"] == forensic["same_day_observation_product_count"] == 138
    assert forensic["classification"] == "stale_snapshot_publication_sequencing"
    assert forensic["db_follow_up_required"] is False


def test_source_pointer_or_opening_change_fails_closed():
    common = dict(pointer_before={"publication_run_id": "a"}, pointer_after={"publication_run_id": "a"},
        rankings_updated_before="r1", rankings_updated_after="r1",
        opening_before={"source_run_fingerprint": "f1", "published_at": "p1"},
        opening_after={"source_run_fingerprint": "f1", "published_at": "p1"})
    publication_v1.assert_source_coherence(**common)
    changed = dict(common); changed["pointer_after"] = {"publication_run_id": "b"}
    with pytest.raises(BenchmarkError, match="changed during assembly"):
        publication_v1.assert_source_coherence(**changed)


def test_dry_run_module_has_no_database_rpc_invocation():
    # Candidate preparation may name the RPC, but Prompt 3A must not call it.
    assert ".rpc(" not in inspect.getsource(publication_v1)
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert artifact["production_counts_before"] == artifact["production_counts_after"]
