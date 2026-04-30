"""Deterministic tests for the Phase 2 RIP Interpretation Engine.

Covers 11 scenarios:
1. Chase-heavy, low safety
2. Mid-tier hit driven
3. Illustration Rare supported
4. Broad value base
5. Single-card dominated
6. All weak
7. All strong
8. Profit high / safety low
9. Profit high / stability low
10. Stability high / profit low
11. Data-limited sections
"""

from __future__ import annotations

import pytest
from backend.interpretation.rips.engine import build_rip_interpretation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_summary(**kwargs):
    """Return a minimal summary dict with defaults for unspecified fields."""
    defaults = {
        "pack_score": 50.0,
        "profit_score": 50.0,
        "safety_score": 50.0,
        "stability_score": 50.0,
        "pack_cost": 5.0,
        "prob_profit": 0.40,
        "prob_big_hit": 0.10,
        "mean_value_to_cost_ratio": 0.95,
        "median_value_to_cost_ratio": 0.80,
        "p95_value_to_cost_ratio": 1.50,
        "roi_percent": -5.0,
        "expected_loss_when_losing_fraction": 0.40,
        "median_loss_when_losing_fraction": 0.40,
        "p05_shortfall_to_cost": 0.40,
        "tail_value_p05": 2.0,
        "expected_loss_when_losing": 2.0,
        "median_loss_when_losing": 2.0,
        "coefficient_of_variation": 1.0,
        "hhi_ev_concentration": 0.10,
        "top1_ev_share": 0.20,
        "top3_ev_share": 0.45,
        "top5_ev_share": 0.60,
        "effective_chase_count": 8.0,
        "expected_loss_per_pack": 1.0,
    }
    defaults.update(kwargs)
    return defaults


def _chase_hits(lead_share=0.60, profile="sir"):
    """Returns a top_hits list dominated by a chase rarity."""
    return [
        {"card_name": "Charizard ex SIR", "ev_contribution": lead_share * 10, "rarity_bucket": "special illustration rare"},
        {"card_name": "Mewtwo ex", "ev_contribution": 0.20 * 10, "rarity_bucket": "ultra rare"},
        {"card_name": "Pikachu ex", "ev_contribution": 0.20 * 10, "rarity_bucket": "ex"},
    ]


def _illustration_hits():
    return [
        {"card_name": "Eevee IR", "ev_contribution": 5.0, "rarity_bucket": "illustration rare"},
        {"card_name": "Sylveon IR", "ev_contribution": 3.0, "rarity_bucket": "illustration rare"},
        {"card_name": "Umbreon ex", "ev_contribution": 2.0, "rarity_bucket": "ultra rare"},
    ]


def _mid_tier_hits():
    return [
        {"card_name": "Gardevoir ex", "ev_contribution": 4.0, "rarity_bucket": "ultra rare"},
        {"card_name": "Lucario ex", "ev_contribution": 3.0, "rarity_bucket": "ex"},
        {"card_name": "Gengar ex", "ev_contribution": 2.5, "rarity_bucket": "double rare"},
        {"card_name": "Absol SIR", "ev_contribution": 0.5, "rarity_bucket": "special illustration rare"},
    ]


def _broad_hits():
    return [
        {"card_name": "Card A", "ev_contribution": 2.0, "rarity_bucket": "special illustration rare"},
        {"card_name": "Card B", "ev_contribution": 2.0, "rarity_bucket": "illustration rare"},
        {"card_name": "Card C", "ev_contribution": 2.0, "rarity_bucket": "ultra rare"},
        {"card_name": "Card D", "ev_contribution": 1.5, "rarity_bucket": "ex"},
        {"card_name": "Card E", "ev_contribution": 1.5, "rarity_bucket": "double rare"},
        {"card_name": "Card F", "ev_contribution": 1.0, "rarity_bucket": "hyper rare"},
    ]


def _rankings_chase_heavy():
    return [
        {"rarity_bucket": "special illustration rare", "total_sampled_value": 800.0, "pulled_count": 20, "avg_sampled_value": 40.0},
        {"rarity_bucket": "ultra rare", "total_sampled_value": 100.0, "pulled_count": 50, "avg_sampled_value": 2.0},
        {"rarity_bucket": "common", "total_sampled_value": 100.0, "pulled_count": 500, "avg_sampled_value": 0.2},
    ]


def _history_improving():
    return [
        {"simulated_mean_pack_value_vs_pack_cost": 0.80, "simulated_median_pack_value_vs_pack_cost": 0.75},
        {"simulated_mean_pack_value_vs_pack_cost": 0.88, "simulated_median_pack_value_vs_pack_cost": 0.80},
        {"simulated_mean_pack_value_vs_pack_cost": 0.95, "simulated_median_pack_value_vs_pack_cost": 0.85},
    ]


def _rip_stats_normal():
    return {
        "pack_paths": {"normal": 800, "special": 200},
        "normal_pack_states": {"basic_hit": 600, "miss": 200},
    }


# ---------------------------------------------------------------------------
# Shared contract assertions
# ---------------------------------------------------------------------------

def _assert_base_contract(result: dict):
    """Every result must satisfy the existing string contract plus meta."""
    assert isinstance(result["packScore"], str), "packScore must be string"
    assert isinstance(result["outcomeDistribution"], str)
    assert isinstance(result["historicalTrend"], str)
    assert isinstance(result["packBreakdown"], str)
    assert isinstance(result["topEvDrivers"], str)
    assert isinstance(result["rarityContribution"], str)
    assert isinstance(result["advancedMetrics"], str)
    assert "meta" in result, "meta key must exist"
    meta = result["meta"]
    for section_key in ("packScore", "profit", "safety", "stability",
                        "outcomeDistribution", "historicalTrend",
                        "packBreakdown", "topEvDrivers", "rarityContribution", "advancedMetrics"):
        assert section_key in meta, f"meta.{section_key} missing"


def _assert_no_premium_led(result: dict):
    """'premium-led' must not appear anywhere in user-facing output."""
    for key in ("packScore", "outcomeDistribution", "historicalTrend",
                "packBreakdown", "topEvDrivers", "rarityContribution", "advancedMetrics"):
        assert "premium-led" not in result[key].lower(), f"'premium-led' found in {key}"

    def _scan(obj):
        if isinstance(obj, str):
            assert "premium-led" not in obj.lower(), f"'premium-led' found in meta: {obj}"
        elif isinstance(obj, dict):
            for v in obj.values():
                _scan(v)
        elif isinstance(obj, list):
            for item in obj:
                _scan(item)

    _scan(result["meta"])


def _assert_meta_structure(meta_section: dict):
    """Each meta section must have required fields."""
    if meta_section is None:
        return
    for field in ("summary", "label", "reason_code", "severity", "confidence", "evidence", "signals"):
        assert field in meta_section, f"meta section missing field: {field}"
    assert isinstance(meta_section["evidence"], list)
    assert isinstance(meta_section["signals"], dict)
    assert meta_section["severity"] in ("positive", "neutral", "caution", "negative", "data_limited")
    assert meta_section["confidence"] in ("high", "medium", "low")


# ---------------------------------------------------------------------------
# Scenario 1: Chase-heavy, low safety
# ---------------------------------------------------------------------------

def test_chase_heavy_low_safety():
    data = {
        "summary": _make_summary(
            profit_score=75.0,
            safety_score=25.0,
            stability_score=55.0,
            p95_value_to_cost_ratio=2.5,
            prob_profit=0.35,
            expected_loss_when_losing_fraction=0.80,
            median_loss_when_losing_fraction=0.75,
            p05_shortfall_to_cost=0.80,
            tail_value_p05=0.50,
        ),
        "top_hits": _chase_hits(),
        "rankings": _rankings_chase_heavy(),
        "history_trend": _history_improving(),
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    _assert_no_premium_led(result)
    for section in result["meta"].values():
        _assert_meta_structure(section)

    # Chase-led EV drivers
    top_ev_meta = result["meta"]["topEvDrivers"]
    assert top_ev_meta["reason_code"] == "chase_led", f"Expected chase_led, got {top_ev_meta['reason_code']}"
    assert "chase" in top_ev_meta["label"].lower()

    # Safety should flag negative/caution
    safety_meta = result["meta"]["safety"]
    assert safety_meta["severity"] in ("negative", "caution")


# ---------------------------------------------------------------------------
# Scenario 2: Mid-tier hit driven
# ---------------------------------------------------------------------------

def test_mid_tier_hit_driven():
    data = {
        "summary": _make_summary(
            profit_score=55.0,
            safety_score=55.0,
            stability_score=60.0,
        ),
        "top_hits": _mid_tier_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    _assert_no_premium_led(result)

    top_ev_meta = result["meta"]["topEvDrivers"]
    # Should be mid_tier_led since ultra rare / ex dominate
    assert top_ev_meta["reason_code"] == "mid_tier_led"
    assert "mid-tier" in top_ev_meta["label"].lower() or "mid-tier" in top_ev_meta["summary"].lower()
    # User-facing label must not say "premium-led"
    assert "premium-led" not in top_ev_meta["label"].lower()
    assert "premium-led" not in top_ev_meta["summary"].lower()


# ---------------------------------------------------------------------------
# Scenario 3: Illustration Rare supported
# ---------------------------------------------------------------------------

def test_illustration_rare_supported():
    data = {
        "summary": _make_summary(
            profit_score=60.0,
            safety_score=60.0,
            stability_score=65.0,
        ),
        "top_hits": _illustration_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    _assert_no_premium_led(result)

    top_ev_meta = result["meta"]["topEvDrivers"]
    assert top_ev_meta["reason_code"] == "illustration_led"
    assert "art" in top_ev_meta["label"].lower() or "art" in top_ev_meta["summary"].lower()


# ---------------------------------------------------------------------------
# Scenario 4: Broad value base
# ---------------------------------------------------------------------------

def test_broad_value_base():
    data = {
        "summary": _make_summary(
            profit_score=65.0,
            safety_score=60.0,
            stability_score=70.0,
            effective_chase_count=14.0,
            hhi_ev_concentration=0.08,
            top1_ev_share=0.12,
            coefficient_of_variation=0.8,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    _assert_no_premium_led(result)

    top_ev_meta = result["meta"]["topEvDrivers"]
    # Broad spread across 3+ rarity groups
    assert top_ev_meta["reason_code"] in ("broad_spread", "mid_tier_led", "illustration_led")

    stability_meta = result["meta"]["stability"]
    assert stability_meta["severity"] in ("positive", "neutral")


# ---------------------------------------------------------------------------
# Scenario 5: Single-card dominated
# ---------------------------------------------------------------------------

def test_single_card_dominated():
    data = {
        "summary": _make_summary(
            stability_score=20.0,
            top1_ev_share=0.65,
            top3_ev_share=0.85,
            hhi_ev_concentration=0.45,
            effective_chase_count=2.0,
        ),
        "top_hits": [
            {"card_name": "Giratina SIR", "ev_contribution": 6.5, "rarity_bucket": "special illustration rare"},
            {"card_name": "Other", "ev_contribution": 1.0, "rarity_bucket": "ultra rare"},
            {"card_name": "Other2", "ev_contribution": 0.5, "rarity_bucket": "common"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    _assert_no_premium_led(result)

    stability_meta = result["meta"]["stability"]
    assert stability_meta["reason_code"] in ("single_card_dominance", "volatile_concentrated", "top_heavy_concentration")

    top_ev_meta = result["meta"]["topEvDrivers"]
    assert top_ev_meta["signals"]["concentration_risk"] is True


# ---------------------------------------------------------------------------
# Scenario 6: All weak
# ---------------------------------------------------------------------------

def test_all_weak():
    data = {
        "summary": _make_summary(
            pack_score=18.0,
            profit_score=18.0,
            safety_score=20.0,
            stability_score=15.0,
            prob_profit=0.20,
            p95_value_to_cost_ratio=0.90,
            median_value_to_cost_ratio=0.55,
            roi_percent=-30.0,
            expected_loss_when_losing_fraction=0.75,
            median_loss_when_losing_fraction=0.70,
        ),
        "top_hits": [],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    _assert_no_premium_led(result)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] == "all_weak"
    assert pack_meta["severity"] == "negative"
    assert "rough" in result["packScore"].lower() or "limited" in result["packScore"].lower()


# ---------------------------------------------------------------------------
# Scenario 7: All strong
# ---------------------------------------------------------------------------

def test_all_strong():
    data = {
        "summary": _make_summary(
            pack_score=85.0,
            profit_score=82.0,
            safety_score=78.0,
            stability_score=80.0,
            prob_profit=0.65,
            p95_value_to_cost_ratio=2.8,
            median_value_to_cost_ratio=1.05,
            roi_percent=12.0,
            expected_loss_when_losing_fraction=0.20,
            effective_chase_count=15.0,
            hhi_ev_concentration=0.06,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": _history_improving(),
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    _assert_no_premium_led(result)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] == "all_strong"
    assert pack_meta["severity"] == "positive"
    assert "better" in result["packScore"].lower() or "strong" in result["packScore"].lower() or "well-rounded" in result["packScore"].lower()


# ---------------------------------------------------------------------------
# Scenario 8: Profit high / safety low
# ---------------------------------------------------------------------------

def test_profit_high_safety_low():
    data = {
        "summary": _make_summary(
            profit_score=80.0,
            safety_score=22.0,
            stability_score=60.0,
            p95_value_to_cost_ratio=2.5,
            expected_loss_when_losing_fraction=0.80,
            median_loss_when_losing_fraction=0.75,
            p05_shortfall_to_cost=0.82,
            tail_value_p05=0.40,
        ),
        "top_hits": _chase_hits(),
        "rankings": _rankings_chase_heavy(),
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    _assert_no_premium_led(result)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] in (
        "profit_strong_safety_weak",
        "high_upside_downside_pressure",
        "profit_led_safety_weak",
    ), f"Unexpected reason_code: {pack_meta['reason_code']}"
    assert pack_meta["severity"] in ("caution", "negative")
    assert "upside" in result["packScore"].lower() or "loss" in result["packScore"].lower() or "painful" in result["packScore"].lower() or "hurt" in result["packScore"].lower()


# ---------------------------------------------------------------------------
# Scenario 9: Profit high / stability low
# ---------------------------------------------------------------------------

def test_profit_high_stability_low():
    data = {
        "summary": _make_summary(
            profit_score=78.0,
            safety_score=55.0,
            stability_score=18.0,
            p95_value_to_cost_ratio=2.2,
            top1_ev_share=0.55,
            top3_ev_share=0.80,
            hhi_ev_concentration=0.35,
            coefficient_of_variation=2.0,
            effective_chase_count=3.0,
        ),
        "top_hits": _chase_hits(lead_share=0.70),
        "rankings": _rankings_chase_heavy(),
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    _assert_no_premium_led(result)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] in (
        "profit_strong_stability_weak",
        "profit_high_stability_constrained",
        "profit_led_stability_weak",
    ), f"Unexpected reason_code: {pack_meta['reason_code']}"
    assert "volatile" in result["packScore"].lower() or "unstable" in result["packScore"].lower() or "concentrated" in result["packScore"].lower() or "swing" in result["packScore"].lower()


# ---------------------------------------------------------------------------
# Scenario 10: Stability high / profit low
# ---------------------------------------------------------------------------

def test_stability_high_profit_low():
    data = {
        "summary": _make_summary(
            profit_score=22.0,
            safety_score=55.0,
            stability_score=80.0,
            p95_value_to_cost_ratio=1.10,
            prob_profit=0.28,
            median_value_to_cost_ratio=0.60,
            roi_percent=-20.0,
            coefficient_of_variation=0.5,
            hhi_ev_concentration=0.07,
            effective_chase_count=12.0,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    _assert_no_premium_led(result)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] in (
        "stability_strong_profit_weak",
        "stable_low_profit",
        "stability_led_profit_weak",
    ), f"Unexpected reason_code: {pack_meta['reason_code']}"
    assert "consistent" in result["packScore"].lower() or "stable" in result["packScore"].lower() or "predictable" in result["packScore"].lower()


# ---------------------------------------------------------------------------
# Scenario 11: Data-limited sections
# ---------------------------------------------------------------------------

def test_data_limited_sections():
    """When data is mostly empty, sections should gracefully return data_limited severity."""
    data = {
        "summary": {},
        "top_hits": [],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    _assert_no_premium_led(result)

    # All sections should still have required meta fields
    for section_key, section_val in result["meta"].items():
        _assert_meta_structure(section_val)

    # Sections with no data should have data_limited or low confidence
    for key in ("topEvDrivers", "rarityContribution", "historicalTrend", "packBreakdown"):
        section = result["meta"][key]
        assert section["severity"] == "data_limited" or section["confidence"] == "low", \
            f"{key} should be data_limited or low confidence when data is missing"

    # String keys must still be non-empty strings
    for key in ("packScore", "outcomeDistribution", "historicalTrend", "packBreakdown",
                "topEvDrivers", "rarityContribution", "advancedMetrics"):
        assert result[key], f"String key {key} must be non-empty"
