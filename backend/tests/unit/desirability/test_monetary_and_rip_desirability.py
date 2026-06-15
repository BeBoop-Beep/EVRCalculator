import pytest

from backend.desirability.monetary_chase_appeal import compute_monetary_chase_appeal
from backend.desirability.rip_desirability import compute_rip_desirability


def test_monetary_chase_appeal_returns_bounded_score_and_breakdown():
    result = compute_monetary_chase_appeal(_high_upside_inputs())

    assert 0.0 <= result["monetary_chase_appeal_score"] <= 100.0
    assert result["monetary_data_quality"] == "usable"
    assert result["component_scores_json"]["components"]
    assert result["component_scores_json"]["weights"]["big_hit_upside_component"] == pytest.approx(0.30)
    assert "top_card_value" in result["component_scores_json"]["available_input_fields"]
    assert "prob_big_hit" in result["component_scores_json"]["available_input_fields"]


def test_monetary_chase_appeal_missing_inputs_returns_none_and_missing_quality():
    result = compute_monetary_chase_appeal({})

    assert result["monetary_chase_appeal_score"] is None
    assert result["monetary_data_quality"] == "missing"
    assert result["component_scores_json"]["available_input_fields"] == []
    assert "prob_big_hit" in result["component_scores_json"]["missing_input_fields"]


def test_partial_inputs_score_only_when_core_signals_exist():
    partial = compute_monetary_chase_appeal(
        {
            "p95_value_to_cost_ratio": 2.0,
            "prob_big_hit": 0.015,
        }
    )
    not_enough = compute_monetary_chase_appeal({"prob_big_hit": 0.015})

    assert partial["monetary_data_quality"] == "partial"
    assert partial["monetary_chase_appeal_score"] is not None
    assert not_enough["monetary_data_quality"] == "missing"
    assert not_enough["monetary_chase_appeal_score"] is None


def test_big_hit_probability_anchor_makes_one_point_five_percent_meaningful():
    result = compute_monetary_chase_appeal(
        {
            "p95_value_to_cost_ratio": 2.0,
            "prob_big_hit": 0.015,
        }
    )

    probability_component = result["component_scores_json"]["components"]["big_hit_probability_component"]
    assert probability_component == pytest.approx(50.0)
    assert result["component_scores_json"]["anchors"]["big_hit_probability_component"]["max"] == pytest.approx(0.03)


def test_high_top_card_upside_scores_above_flat_low_upside_set():
    high = compute_monetary_chase_appeal(_high_upside_inputs())
    low = compute_monetary_chase_appeal(
        {
            "pack_cost": 5.0,
            "top_card_value": 8.0,
            "top_3_card_value": 20.0,
            "top_5_card_value": 30.0,
            "prob_big_hit": 0.04,
            "p95_value_to_cost_ratio": 0.8,
            "p99_value_to_cost_ratio": 1.2,
            "hit_ev_per_pack": 0.7,
            "mean_value_to_cost_ratio": 0.35,
            "effective_chase_count": 4.0,
            "hhi_ev_concentration": 0.30,
            "top1_ev_share": 0.35,
            "top3_ev_share": 0.65,
            "top5_ev_share": 0.85,
        }
    )

    assert high["monetary_chase_appeal_score"] > low["monetary_chase_appeal_score"]


def test_chase_depth_and_concentration_components_distinguish_broad_from_single_card_heavy():
    broad = compute_monetary_chase_appeal(
        {
            **_shared_monetary_inputs(),
            "effective_chase_count": 28.0,
            "hhi_ev_concentration": 0.04,
            "top1_ev_share": 0.08,
            "top3_ev_share": 0.22,
            "top5_ev_share": 0.35,
        }
    )
    single_card_heavy = compute_monetary_chase_appeal(
        {
            **_shared_monetary_inputs(),
            "effective_chase_count": 2.0,
            "hhi_ev_concentration": 0.50,
            "top1_ev_share": 0.62,
            "top3_ev_share": 0.86,
            "top5_ev_share": 0.94,
        }
    )

    broad_components = broad["component_scores_json"]["components"]
    heavy_components = single_card_heavy["component_scores_json"]["components"]
    assert broad_components["chase_depth_component"] > heavy_components["chase_depth_component"]
    assert broad_components["concentration_component"] > heavy_components["concentration_component"]


def test_rip_desirability_blend_math_is_correct():
    result = compute_rip_desirability(
        pure_desirability_score=80.0,
        monetary_chase_appeal_score=50.0,
    )

    assert result["rip_desirability_score_80_20"] == pytest.approx(74.0)
    assert result["rip_desirability_score_70_30"] == pytest.approx(71.0)
    assert result["rip_desirability_score_60_40"] == pytest.approx(68.0)
    assert result["primary_rip_desirability_score"] == result["rip_desirability_score_70_30"]


def test_rip_desirability_returns_none_when_monetary_is_missing():
    result = compute_rip_desirability(
        pure_desirability_score=80.0,
        monetary_chase_appeal_score=None,
    )

    assert result["rip_desirability_score_80_20"] is None
    assert result["rip_desirability_score_70_30"] is None
    assert result["rip_desirability_score_60_40"] is None
    assert result["primary_rip_desirability_score"] is None


def test_rip_desirability_does_not_change_pure_desirability():
    pure_score = 91.1709
    result = compute_rip_desirability(
        pure_desirability_score=pure_score,
        monetary_chase_appeal_score=40.0,
    )

    assert result["pure_desirability_score"] == pure_score
    assert result["pure_desirability_score"] != result["primary_rip_desirability_score"]


def _high_upside_inputs():
    return {
        "pack_cost": 5.0,
        "top_card_value": 300.0,
        "top_3_card_value": 520.0,
        "top_5_card_value": 720.0,
        "prob_big_hit": 0.18,
        "p95_value_to_cost_ratio": 4.0,
        "p99_value_to_cost_ratio": 9.0,
        "hit_ev_per_pack": 4.0,
        "mean_value_to_cost_ratio": 0.95,
        "effective_chase_count": 18.0,
        "hhi_ev_concentration": 0.12,
        "top1_ev_share": 0.22,
        "top3_ev_share": 0.45,
        "top5_ev_share": 0.60,
    }


def _shared_monetary_inputs():
    return {
        "pack_cost": 5.0,
        "top_card_value": 120.0,
        "top_3_card_value": 270.0,
        "top_5_card_value": 390.0,
        "prob_big_hit": 0.12,
        "p95_value_to_cost_ratio": 3.0,
        "p99_value_to_cost_ratio": 6.0,
        "hit_ev_per_pack": 2.2,
        "mean_value_to_cost_ratio": 0.75,
    }
