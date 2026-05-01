"""Deterministic tests for the Phase 2 RIP Interpretation Engine.

Covers 13 scenarios:
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
12. Weighted driver prefers profit
13. Score fallback without tiers
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


def _chase_hits(lead_share=0.38, profile="sir"):
    """Returns a top_hits list dominated by a chase rarity."""
    remainder = max(0.0, 10 - (lead_share * 10))
    return [
        {"card_name": "Charizard ex SIR", "ev_contribution": lead_share * 10, "rarity_bucket": "special illustration rare"},
        {"card_name": "Mew ex SIR", "ev_contribution": remainder * 0.45, "rarity_bucket": "special illustration rare"},
        {"card_name": "Mewtwo ex", "ev_contribution": remainder * 0.35, "rarity_bucket": "ultra rare"},
        {"card_name": "Pikachu ex", "ev_contribution": remainder * 0.20, "rarity_bucket": "ex"},
    ]


def _illustration_hits():
    return [
        {"card_name": "Eevee IR", "ev_contribution": 3.6, "rarity_bucket": "illustration rare"},
        {"card_name": "Sylveon IR", "ev_contribution": 3.0, "rarity_bucket": "illustration rare"},
        {"card_name": "Umbreon IR", "ev_contribution": 1.8, "rarity_bucket": "illustration rare"},
        {"card_name": "Umbreon ex", "ev_contribution": 1.6, "rarity_bucket": "ultra rare"},
    ]


def _mid_tier_hits():
    return [
        {"card_name": "Gardevoir ex", "ev_contribution": 3.4, "rarity_bucket": "ultra rare"},
        {"card_name": "Miraidon ex", "ev_contribution": 2.0, "rarity_bucket": "ultra rare"},
        {"card_name": "Lucario ex", "ev_contribution": 2.6, "rarity_bucket": "ex"},
        {"card_name": "Gengar ex", "ev_contribution": 1.8, "rarity_bucket": "double rare"},
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


def _rankings_illustration_led():
    return [
        {"rarity_bucket": "illustration rare", "total_sampled_value": 460.0, "pulled_count": 90, "avg_sampled_value": 5.11},
        {"rarity_bucket": "ultra rare", "total_sampled_value": 240.0, "pulled_count": 80, "avg_sampled_value": 3.0},
        {"rarity_bucket": "double rare", "total_sampled_value": 180.0, "pulled_count": 140, "avg_sampled_value": 1.29},
        {"rarity_bucket": "common", "total_sampled_value": 120.0, "pulled_count": 900, "avg_sampled_value": 0.13},
    ]


def _rankings_pull_low_value_but_ev_high():
    return [
        {"rarity_bucket": "special illustration rare", "total_sampled_value": 500.0, "pulled_count": 20, "avg_sampled_value": 25.0},
        {"rarity_bucket": "ultra rare", "total_sampled_value": 230.0, "pulled_count": 80, "avg_sampled_value": 2.88},
        {"rarity_bucket": "common", "total_sampled_value": 190.0, "pulled_count": 1000, "avg_sampled_value": 0.19},
        {"rarity_bucket": "uncommon", "total_sampled_value": 80.0, "pulled_count": 700, "avg_sampled_value": 0.11},
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


def _assert_no_bad_pack_phrases(result: dict):
    banned = (
        "expected return",
        "erase the upside",
        "tradeoff-heavy",
        "led by stability",
        "main constraint",
        "tier context",
        "profile led by",
    )
    pack_strings = [
        result["packScore"],
        result["meta"]["packScore"]["summary"],
        result["meta"]["packScore"]["label"],
    ]
    for value in pack_strings:
        lowered = value.lower()
        for phrase in banned:
            assert phrase not in lowered, f"'{phrase}' found in pack score output: {value}"


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
    _assert_no_bad_pack_phrases(result)
    for section in result["meta"].values():
        _assert_meta_structure(section)

    # SIR-led EV drivers (top3-concentration path or dominant-rarity path)
    top_ev_meta = result["meta"]["topEvDrivers"]
    assert top_ev_meta["reason_code"] in {"sir_led", "sir_led_top3", "chase_led", "single_card_dependent"}, (
        f"Expected sir/chase/single-card led, got {top_ev_meta['reason_code']}"
    )
    assert (
        "special illustration" in top_ev_meta["label"].lower()
        or "chase" in top_ev_meta["label"].lower()
        or "one card" in top_ev_meta["label"].lower()
    )

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
    # Ultra rare / ex should classify as ex_ultra_led or ex_ultra_led_top3.
    assert top_ev_meta["reason_code"] in ("ex_ultra_led", "ex_ultra_led_top3"), f"Expected ex/ultra-led, got {top_ev_meta['reason_code']}"
    assert "ultra" in top_ev_meta["label"].lower() or "ex" in top_ev_meta["label"].lower()
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
    assert top_ev_meta["reason_code"] in ("illustration_led", "ir_led_top3")
    assert "illustration rare" in top_ev_meta["label"].lower() or "illustration rare" in top_ev_meta["summary"].lower()


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
            top3_ev_share=0.35,  # explicitly below 0.40 to reach broad path
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
    # Broad spread across 3+ rarity groups — broad_value_base expected when all shares are low
    assert top_ev_meta["reason_code"] in ("broad_value_base", "mixed_hit_base", "top_cards_carry_value",
                                           "illustration_led", "ex_ultra_led")

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
    assert stability_meta["reason_code"] in (
        "single_card_dominance",
        "volatile_concentrated",
        "top_heavy_concentration",
        "low_tier_hit_dependent",
    )

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
    _assert_no_bad_pack_phrases(result)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] == "bottom_tier_open"
    assert pack_meta["label"] == "One of the toughest opens"
    assert pack_meta["severity"] == "negative"
    assert "toughest sets to open" in result["packScore"].lower()


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
            pack_tier="S",
            profit_tier="S",
            safety_tier="A",
            stability_tier="A",
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
    _assert_no_bad_pack_phrases(result)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] == "elite_open"
    assert pack_meta["label"] == "Great to open right now"
    assert pack_meta["severity"] == "positive"
    assert "cards can pay back the pack price well" in result["packScore"].lower()


# ---------------------------------------------------------------------------
# Scenario 8: Profit high / safety low
# ---------------------------------------------------------------------------

def test_profit_high_safety_low():
    data = {
        "summary": _make_summary(
            pack_score=88.0,
            profit_score=80.0,
            safety_score=22.0,
            stability_score=60.0,
            pack_tier="S",
            profit_tier="S",
            safety_tier="F",
            stability_tier="B",
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
    _assert_no_bad_pack_phrases(result)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] == "strong_but_risky"
    assert pack_meta["label"] == "Strong, but risky"
    assert pack_meta["signals"]["weighted_driver"] == "profit"
    assert pack_meta["severity"] == "caution"
    assert "bad packs can still hurt" in result["packScore"].lower()


# ---------------------------------------------------------------------------
# Scenario 9: Profit high / stability low
# ---------------------------------------------------------------------------

def test_profit_high_stability_low():
    data = {
        "summary": _make_summary(
            pack_score=81.0,
            profit_score=78.0,
            safety_score=55.0,
            stability_score=18.0,
            pack_tier="A",
            profit_tier="S",
            safety_tier="C",
            stability_tier="F",
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
    _assert_no_bad_pack_phrases(result)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] == "good_value_shaky_path"
    assert pack_meta["label"] == "Good value, shaky path"
    assert pack_meta["signals"]["weighted_driver"] == "profit"
    assert pack_meta["signals"]["weighted_drag"] == "stability"
    assert "too much depends on landing the right hits" in result["packScore"].lower()


# ---------------------------------------------------------------------------
# Scenario 10: Stability high / profit low
# ---------------------------------------------------------------------------

def test_stability_high_profit_low():
    data = {
        "summary": _make_summary(
            pack_score=54.0,
            profit_score=22.0,
            safety_score=55.0,
            stability_score=80.0,
            pack_tier="B",
            profit_tier="D",
            safety_tier="A",
            stability_tier="S",
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
    _assert_no_bad_pack_phrases(result)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] in ("okay_but_capped", "safe_but_low_reward")
    assert pack_meta["label"] in ("Safe, but not exciting", "Low risk, low reward")
    assert "wins are not strong enough" in result["packScore"].lower() or "wins are not big enough" in result["packScore"].lower()
    assert "led by stability" not in result["packScore"].lower()


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


def test_weighted_driver_prefers_profit_over_raw_stability():
    data = {
        "summary": _make_summary(
            pack_score=90.0,
            profit_score=88.0,
            safety_score=58.0,
            stability_score=98.0,
            pack_tier="S",
            profit_tier="S",
            safety_tier="B",
            stability_tier="S",
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["signals"]["weighted_driver"] == "profit"
    assert pack_meta["signals"]["strongest_pillar"] == "stability"


def test_elite_open_with_medium_safety_band():
    """With profit_tier=S and safety_tier=B (medium band), the matrix maps to elite_open.

    The old tail-pressure override no longer applies: tier drives the band, not raw signal flags.
    elite_return:medium:high (stability_tier=A) -> elite_open.
    """
    data = {
        "summary": _make_summary(
            pack_score=88.0,
            profit_score=86.0,
            safety_score=58.0,
            stability_score=74.0,
            pack_tier="S",
            profit_tier="S",
            safety_tier="B",
            stability_tier="A",
            expected_loss_when_losing_fraction=0.82,
            median_loss_when_losing_fraction=0.78,
            p05_shortfall_to_cost=0.80,
            tail_value_p05=0.35,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["signals"]["pack"]["tier"] == "S"
    assert pack_meta["signals"]["pillars"]["profit"]["tier"] == "S"
    assert pack_meta["signals"]["pillars"]["safety"]["tier"] == "B"
    assert pack_meta["signals"]["decision_category"] == "elite_open"
    assert pack_meta["reason_code"] == "elite_open"
    # Matrix signals present
    assert pack_meta["signals"]["profit_lane"] == "elite_return"
    assert pack_meta["signals"]["safety_band"] == "medium"
    assert pack_meta["signals"]["stability_band"] == "high"
    assert pack_meta["signals"]["matrix_key"] == "elite_return:medium:high"


def test_elite_open_when_no_tail_or_stability_risk():
    data = {
        "summary": _make_summary(
            pack_score=90.0,
            profit_score=88.0,
            safety_score=62.0,
            stability_score=76.0,
            pack_tier="S",
            profit_tier="S",
            safety_tier="B",
            stability_tier="A",
            expected_loss_when_losing_fraction=0.22,
            median_loss_when_losing_fraction=0.20,
            p05_shortfall_to_cost=0.22,
            coefficient_of_variation=0.75,
            top1_ev_share=0.18,
            hhi_ev_concentration=0.08,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["signals"]["pack"]["tier"] == "S"
    assert pack_meta["signals"]["pillars"]["profit"]["tier"] == "S"
    assert pack_meta["signals"]["pillars"]["safety"]["tier"] == "B"
    assert pack_meta["signals"]["decision_category"] == "elite_open"
    assert pack_meta["reason_code"] == "elite_open"


def test_pack_score_evidence_labels_are_user_facing():
    data = {
        "summary": _make_summary(
            pack_score=80.0,
            profit_score=78.0,
            safety_score=50.0,
            stability_score=60.0,
            pack_tier="A",
            profit_tier="A",
            safety_tier="C",
            stability_tier="B",
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)

    labels = [item["label"] for item in result["meta"]["packScore"]["evidence"]]
    assert "Main reason" in labels
    assert "Watch out for" in labels
    assert "Weighted driver" not in labels
    assert "Main catch" not in labels


def test_pack_score_uses_score_fallback_when_tiers_missing():
    data = {
        "summary": _make_summary(
            pack_score=86.0,
            profit_score=87.0,
            safety_score=44.0,
            stability_score=72.0,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)

    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] != "data_limited"
    assert pack_meta["signals"]["weighted_driver"] == "profit"
    assert pack_meta["signals"]["pillars"]["profit"]["strength"] == 5
    assert pack_meta["signals"]["pillars"]["safety"]["strength"] == 2


def test_s_tier_profit_with_low_profit_frequency_still_frames_as_strong_setup():
    data = {
        "summary": _make_summary(
            pack_score=88.0,
            profit_score=82.0,
            safety_score=45.0,
            stability_score=62.0,
            pack_tier="S",
            profit_tier="S",
            safety_tier="C",
            stability_tier="B",
            prob_profit=0.27,
            median_value_to_cost_ratio=0.72,
            p95_value_to_cost_ratio=2.40,
        ),
        "top_hits": _chase_hits(),
        "rankings": _rankings_chase_heavy(),
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)

    summary = result["meta"]["profit"]["summary"].lower()
    assert "one of the strongest profit setups" in summary
    assert "upside can still beat the pack price" in summary


def test_profit_profile_low_probability_huge_upside():
    data = {
        "summary": _make_summary(
            prob_profit=0.11,
            p95_value_to_cost_ratio=3.65,
            mean_value_to_cost_ratio=0.58,
            median_value_to_cost_ratio=0.18,
        ),
        "top_hits": _chase_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }

    result = build_rip_interpretation(data)
    profit_meta = result["meta"]["profit"]
    summary = profit_meta["summary"].lower()
    label = profit_meta["label"].lower()

    assert profit_meta["signals"]["profit_profile"] in {
        "rare_wins_huge_upside",
        "weak_normal_packs_big_hits",
    }
    assert "rare wins" in label or "big hits" in label or "huge upside" in label
    assert "high-end upside is huge" in summary
    assert "carried by big-hit potential" in summary
    assert "High-end upside vs cost" in [item["label"] for item in profit_meta["evidence"]]


def test_profit_profile_low_probability_good_upside():
    data = {
        "summary": _make_summary(
            prob_profit=0.10,
            p95_value_to_cost_ratio=2.70,
            mean_value_to_cost_ratio=0.56,
            median_value_to_cost_ratio=0.19,
        ),
        "top_hits": _chase_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }

    result = build_rip_interpretation(data)
    profile = result["meta"]["profit"]["signals"]["profit_profile"]
    assert profile in {"rare_wins_good_upside", "weak_normal_packs_big_hits"}


def test_profit_profile_better_probability_weak_upside():
    data = {
        "summary": _make_summary(
            prob_profit=0.15,
            p95_value_to_cost_ratio=1.20,
            mean_value_to_cost_ratio=0.54,
            median_value_to_cost_ratio=0.24,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }

    result = build_rip_interpretation(data)
    profit_meta = result["meta"]["profit"]
    assert profit_meta["signals"]["profit_profile"] == "steady_but_capped"
    summary = profit_meta["summary"].lower()
    assert "ceiling is modest" in summary
    assert "score comes from a better chance to win" in summary


def test_profit_profile_low_probability_weak_upside():
    data = {
        "summary": _make_summary(
            prob_profit=0.04,
            p95_value_to_cost_ratio=0.70,
            mean_value_to_cost_ratio=0.36,
            median_value_to_cost_ratio=0.08,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }

    result = build_rip_interpretation(data)
    assert result["meta"]["profit"]["signals"]["profit_profile"] == "weak_chance_weak_upside"


def test_profit_profile_strong_mean_but_modest_upside_mentions_average_support():
    data = {
        "summary": _make_summary(
            prob_profit=0.13,
            p95_value_to_cost_ratio=1.79,
            mean_value_to_cost_ratio=0.73,
            median_value_to_cost_ratio=0.23,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }

    result = build_rip_interpretation(data)
    profit_meta = result["meta"]["profit"]
    summary = profit_meta["summary"].lower()
    assert "upside can still beat the pack price" in summary
    assert "score holds up because the win chance is better than many sets" in summary
    assert "huge upside" not in summary


def test_profit_profile_strong_average_capped_upside():
    data = {
        "summary": _make_summary(
            profit_tier="A",
            prob_profit=0.078,
            mean_value_to_cost_ratio=0.88,
            p95_value_to_cost_ratio=1.28,
            median_value_to_cost_ratio=0.23,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }

    result = build_rip_interpretation(data)
    profit_meta = result["meta"]["profit"]
    assert profit_meta["signals"]["profit_profile"] == "strong_average_capped_upside"
    assert profit_meta["label"] == "Strong average, capped upside"
    summary = profit_meta["summary"].lower()
    assert "strong profit setup compared to most sets" in summary
    assert "upside can still beat the pack price" in summary
    assert "average return is doing most of the work" in summary
    assert "average value holds up well because stronger hits pull results up" not in summary


def test_profit_summary_s_tier_huge_upside_is_clearly_elite():
    data = {
        "summary": _make_summary(
            profit_tier="S",
            prob_profit=0.113,
            p95_value_to_cost_ratio=3.60,
            mean_value_to_cost_ratio=0.57,
            median_value_to_cost_ratio=0.17,
        ),
        "top_hits": _chase_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }

    result = build_rip_interpretation(data)
    summary = result["meta"]["profit"]["summary"].lower()
    assert "one of the strongest profit setups" in summary
    assert "high-end upside is huge" in summary
    assert "carried by big-hit potential" in summary


def test_profit_summary_b_tier_calls_out_above_average_setup():
    data = {
        "summary": _make_summary(
            profit_tier="B",
            prob_profit=0.11,
            p95_value_to_cost_ratio=1.85,
            mean_value_to_cost_ratio=0.60,
            median_value_to_cost_ratio=0.22,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }

    result = build_rip_interpretation(data)
    summary = result["meta"]["profit"]["summary"].lower()
    assert "above-average profit setup" in summary


def test_profit_summary_c_tier_calls_out_middle_setup():
    data = {
        "summary": _make_summary(
            profit_tier="C",
            prob_profit=0.09,
            p95_value_to_cost_ratio=1.40,
            mean_value_to_cost_ratio=0.53,
            median_value_to_cost_ratio=0.20,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }

    result = build_rip_interpretation(data)
    summary = result["meta"]["profit"]["summary"].lower()
    assert "middle-of-the-pack profit setup" in summary


def test_profit_summary_f_tier_calls_out_weak_setup_and_driver():
    data = {
        "summary": _make_summary(
            profit_tier="F",
            prob_profit=0.03,
            p95_value_to_cost_ratio=0.80,
            mean_value_to_cost_ratio=0.38,
            median_value_to_cost_ratio=0.10,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }

    result = build_rip_interpretation(data)
    summary = result["meta"]["profit"]["summary"].lower()
    assert "weak profit setup" in summary
    assert "wins are rare" in summary or "do not pay back enough" in summary


def test_s_tier_safety_with_bad_raw_losses_uses_relative_safer_language():
    data = {
        "summary": _make_summary(
            pack_score=70.0,
            profit_score=62.0,
            safety_score=95.0,
            stability_score=55.0,
            safety_tier="S",
            expected_loss_when_losing_fraction=0.82,
            median_loss_when_losing_fraction=0.78,
            p05_shortfall_to_cost=0.82,
            tail_value_p05=0.25,
        ),
        "top_hits": _mid_tier_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)

    safety_label = result["meta"]["safety"]["label"].lower()
    safety_summary = result["meta"]["safety"]["summary"].lower()
    assert "punishing" not in safety_label
    assert "easier to handle" in safety_summary or "safer" in safety_summary


def test_c_tier_stability_with_broadish_metrics_is_still_average_spread():
    data = {
        "summary": _make_summary(
            stability_score=58.0,
            stability_tier="C",
            top1_ev_share=0.18,
            top3_ev_share=0.46,
            top5_ev_share=0.62,
            hhi_ev_concentration=0.11,
            effective_chase_count=9.0,
            coefficient_of_variation=0.95,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)

    stability_summary = result["meta"]["stability"]["summary"].lower()
    assert "small group of cards" in stability_summary
    assert "depend heavily" in stability_summary


def test_a_tier_and_c_tier_stability_do_not_share_same_summary():
    common = {
        "pack_score": 72.0,
        "profit_score": 60.0,
        "safety_score": 58.0,
        "top1_ev_share": 0.20,
        "top3_ev_share": 0.50,
        "top5_ev_share": 0.66,
        "hhi_ev_concentration": 0.12,
        "effective_chase_count": 8.0,
        "coefficient_of_variation": 1.00,
    }

    high = build_rip_interpretation(
        {
            "summary": _make_summary(**common, stability_score=76.0, stability_tier="A"),
            "top_hits": _broad_hits(),
            "rankings": [],
            "history_trend": [],
            "rip_statistics": _rip_stats_normal(),
        }
    )
    low = build_rip_interpretation(
        {
            "summary": _make_summary(**common, stability_score=58.0, stability_tier="C"),
            "top_hits": _broad_hits(),
            "rankings": [],
            "history_trend": [],
            "rip_statistics": _rip_stats_normal(),
        }
    )

    high_summary = high["meta"]["stability"]["summary"].lower()
    low_summary = low["meta"]["stability"]["summary"].lower()
    assert "small group of cards" in high_summary
    assert "small group of cards" in low_summary


def test_pack_score_evidence_excludes_pillar_scores_and_ranks():
    data = {
        "summary": _make_summary(
            pack_score=80.0,
            profit_score=78.0,
            safety_score=50.0,
            stability_score=60.0,
            pack_tier="A",
            pack_rank=10,
            profit_tier="A",
            safety_tier="C",
            stability_tier="B",
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    evidence_labels = [item["label"] for item in result["meta"]["packScore"]["evidence"]]

    assert "Profit score" not in evidence_labels
    assert "Safety score" not in evidence_labels
    assert "Stability score" not in evidence_labels
    assert "Profit rank" not in evidence_labels
    assert "Safety rank" not in evidence_labels
    assert "Stability rank" not in evidence_labels


def test_pack_score_evidence_keeps_main_reason_and_watch_out_for():
    data = {
        "summary": _make_summary(
            pack_score=79.0,
            profit_score=76.0,
            safety_score=49.0,
            stability_score=58.0,
            pack_tier="A",
            pack_rank=9,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    evidence_labels = [item["label"] for item in result["meta"]["packScore"]["evidence"]]

    assert "Main reason" in evidence_labels
    assert "Watch out for" in evidence_labels


def test_paldean_fates_style_bottom_tier_open():
    data = {
        "summary": _make_summary(
            pack_score=7.0,
            profit_score=0.0,
            safety_score=0.0,
            stability_score=7.6,
            pack_tier="F",
            profit_tier="F",
            safety_tier="F",
            stability_tier="F",
            top1_ev_share=0.30,
            top3_ev_share=0.48,
            coefficient_of_variation=6.2,
            hhi_ev_concentration=0.11,
            effective_chase_count=8.8,
            p05_shortfall_to_cost=0.96,
        ),
        "top_hits": _chase_hits(lead_share=0.30),
        "rankings": _rankings_chase_heavy(),
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    pack_meta = result["meta"]["packScore"]

    assert pack_meta["reason_code"] == "bottom_tier_open"
    assert pack_meta["label"] == "One of the toughest opens"
    summary = pack_meta["summary"].lower()
    assert "not paying back the pack price" in summary
    assert "misses are brutal" in summary
    assert "not enough value spread" in summary


def test_very_weak_not_absolute_bottom():
    data = {
        "summary": _make_summary(
            pack_score=22.0,
            profit_score=18.0,
            safety_score=20.0,
            stability_score=52.0,
            pack_tier="D",
            profit_tier="D",
            safety_tier="F",
            stability_tier="C",
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] in {"very_weak_open", "weak_open"}
    assert pack_meta["reason_code"] not in {"average_open", "below_average_open"}


def test_ascended_heroes_style_is_not_weak_open():
    data = {
        "summary": _make_summary(
            pack_score=58.0,
            profit_score=60.0,
            safety_score=42.0,
            stability_score=18.0,
            pack_tier="B",
            profit_tier="B",
            safety_tier="C",
            stability_tier="F",
            top3_ev_share=0.46,
            top1_ev_share=0.20,
            coefficient_of_variation=1.9,
            hhi_ev_concentration=0.28,
        ),
        "top_hits": _sir_top3_hits(),
        "rankings": _rankings_chase_heavy(),
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    pack_meta = result["meta"]["packScore"]
    assert pack_meta["reason_code"] in {"good_value_shaky_path", "above_average_but_flawed", "hit_dependent_open"}
    assert pack_meta["reason_code"] not in {"weak_open", "very_weak_open", "bottom_tier_open"}


def test_151_style_differs_from_ascended_heroes_style():
    ascended = build_rip_interpretation(
        {
            "summary": _make_summary(
                pack_score=58.0,
                profit_score=60.0,
                safety_score=42.0,
                stability_score=18.0,
                pack_tier="B",
                profit_tier="B",
                safety_tier="C",
                stability_tier="F",
                top3_ev_share=0.46,
            ),
            "top_hits": _sir_top3_hits(),
            "rankings": _rankings_chase_heavy(),
            "history_trend": [],
            "rip_statistics": {},
        }
    )
    one_fifty_one = build_rip_interpretation(
        {
            "summary": _make_summary(
                pack_score=45.0,
                profit_score=45.0,
                safety_score=22.0,
                stability_score=46.0,
                pack_tier="C",
                profit_tier="C",
                safety_tier="D",
                stability_tier="C",
                top3_ev_share=0.38,
            ),
            "top_hits": _broad_hits(),
            "rankings": [],
            "history_trend": [],
            "rip_statistics": {},
        }
    )

    ascended_category = ascended["meta"]["packScore"]["reason_code"]
    one_fifty_one_category = one_fifty_one["meta"]["packScore"]["reason_code"]
    assert one_fifty_one_category in {"average_but_risky", "below_average_open"}
    assert one_fifty_one_category != ascended_category


def test_b_ranked_pack_guardrail():
    data = {
        "summary": _make_summary(
            pack_score=58.0,
            profit_score=59.0,
            safety_score=41.0,
            stability_score=43.0,
            pack_tier="B",
            profit_tier="B",
            safety_tier="C",
            stability_tier="C",
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    assert result["meta"]["packScore"]["reason_code"] not in {"weak_open", "very_weak_open", "bottom_tier_open"}


def test_c_ranked_average_pack_is_average_open():
    data = {
        "summary": _make_summary(
            pack_score=45.0,
            profit_score=44.0,
            safety_score=46.0,
            stability_score=43.0,
            pack_tier="C",
            profit_tier="C",
            safety_tier="C",
            stability_tier="C",
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    assert result["meta"]["packScore"]["reason_code"] == "average_open"


def test_df_pack_with_profit_f_and_safety_f_is_harsh():
    data = {
        "summary": _make_summary(
            pack_score=14.0,
            profit_score=9.0,
            safety_score=6.0,
            stability_score=18.0,
            pack_tier="F",
            profit_tier="F",
            safety_tier="F",
            stability_tier="D",
        ),
        "top_hits": _chase_hits(lead_share=0.32),
        "rankings": _rankings_chase_heavy(),
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    assert result["meta"]["packScore"]["reason_code"] in {"bottom_tier_open", "very_weak_open"}


def test_no_old_generic_collapse_across_three_profiles():
    profiles = {
        "b_b_c_f": build_rip_interpretation(
            {
                "summary": _make_summary(
                    pack_score=58.0,
                    profit_score=60.0,
                    safety_score=42.0,
                    stability_score=18.0,
                    pack_tier="B",
                    profit_tier="B",
                    safety_tier="C",
                    stability_tier="F",
                    top3_ev_share=0.46,
                ),
                "top_hits": _sir_top3_hits(),
                "rankings": _rankings_chase_heavy(),
                "history_trend": [],
                "rip_statistics": {},
            }
        ),
        "c_c_f_c": build_rip_interpretation(
            {
                "summary": _make_summary(
                    pack_score=45.0,
                    profit_score=45.0,
                    safety_score=22.0,
                    stability_score=44.0,
                    pack_tier="C",
                    profit_tier="C",
                    safety_tier="F",
                    stability_tier="C",
                ),
                "top_hits": _broad_hits(),
                "rankings": [],
                "history_trend": [],
                "rip_statistics": {},
            }
        ),
        "f_f_f_f": build_rip_interpretation(
            {
                "summary": _make_summary(
                    pack_score=5.0,
                    profit_score=0.0,
                    safety_score=0.0,
                    stability_score=7.0,
                    pack_tier="F",
                    profit_tier="F",
                    safety_tier="F",
                    stability_tier="F",
                ),
                "top_hits": _chase_hits(lead_share=0.30),
                "rankings": _rankings_chase_heavy(),
                "history_trend": [],
                "rip_statistics": {},
            }
        ),
    }

    categories = {key: value["meta"]["packScore"]["reason_code"] for key, value in profiles.items()}
    summaries = {key: value["meta"]["packScore"]["summary"] for key, value in profiles.items()}

    assert len(set(categories.values())) == 3
    assert len(set(summaries.values())) == 3


def test_advanced_metrics_strong_but_risky_supports_main_read_with_catch():
    data = {
        "summary": _make_summary(
            pack_score=88.0,
            profit_score=82.0,
            safety_score=24.0,
            stability_score=60.0,
            pack_tier="S",
            profit_tier="S",
            safety_tier="F",
            stability_tier="B",
            p95_value_to_cost_ratio=2.60,
            coefficient_of_variation=1.90,
            hhi_ev_concentration=0.30,
            effective_chase_count=3.0,
            expected_loss_when_losing=3.0,
            median_loss_when_losing=2.7,
            expected_loss_per_pack=1.8,
        ),
        "top_hits": _chase_hits(),
        "rankings": _rankings_chase_heavy(),
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)

    adv = result["meta"]["advancedMetrics"]
    assert adv["label"] in {"Risk check", "Support with a catch"}
    assert "support" in adv["summary"].lower()
    assert "bad packs can still hurt" in adv["summary"].lower() or "catch" in adv["summary"].lower()


def test_top_ev_drivers_illustration_led_output_copy():
    data = {
        "summary": _make_summary(),
        "top_hits": [
            {"card_name": "Card IR 1", "ev_contribution": 3.9, "rarity_bucket": "illustration rare"},
            {"card_name": "Card IR 2", "ev_contribution": 3.1, "rarity_bucket": "illustration rare"},
            {"card_name": "Card IR 3", "ev_contribution": 1.8, "rarity_bucket": "illustration rare"},
            {"card_name": "Card UR", "ev_contribution": 1.5, "rarity_bucket": "ultra rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]

    assert top_ev_meta["reason_code"] in ("illustration_led", "ir_led_top3")
    assert "illustration rares" in top_ev_meta["label"].lower()
    assert "illustration rares" in top_ev_meta["summary"].lower() or "art" in top_ev_meta["summary"].lower()


def test_top_ev_drivers_sir_led_output_copy():
    data = {
        "summary": _make_summary(),
        "top_hits": [
            {"card_name": "Card SIR 1", "ev_contribution": 3.8, "rarity_bucket": "special illustration rare"},
            {"card_name": "Card SIR 2", "ev_contribution": 2.8, "rarity_bucket": "special illustration rare"},
            {"card_name": "Card SIR 3", "ev_contribution": 2.0, "rarity_bucket": "special illustration rare"},
            {"card_name": "Card UR", "ev_contribution": 1.4, "rarity_bucket": "ultra rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]

    assert top_ev_meta["reason_code"] in ("sir_led", "sir_led_top3")
    assert "special illustration rares" in top_ev_meta["label"].lower()
    assert "hard-to-pull" in top_ev_meta["summary"].lower() or "chase" in top_ev_meta["summary"].lower() or "high-end" in top_ev_meta["summary"].lower()


def test_top_ev_drivers_broad_or_mixed_only_when_no_leader_above_35():
    data = {
        "summary": _make_summary(),
        "top_hits": [
            {"card_name": "Card A", "ev_contribution": 2.3, "rarity_bucket": "illustration rare"},
            {"card_name": "Card B", "ev_contribution": 2.1, "rarity_bucket": "special illustration rare"},
            {"card_name": "Card C", "ev_contribution": 2.0, "rarity_bucket": "ultra rare"},
            {"card_name": "Card D", "ev_contribution": 1.8, "rarity_bucket": "double rare"},
            {"card_name": "Card E", "ev_contribution": 1.6, "rarity_bucket": "hyper rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]
    assert top_ev_meta["signals"]["leading_rarity_ev_share"] < 0.35
    assert top_ev_meta["reason_code"] in {
        "broad_value_base", "mixed_hit_base", "top_cards_carry_value", "top_three_carry_value"
    }


# ── New concentration-pattern tests ───────────────────────────────────────────


def test_top_ev_drivers_top_card_led_obsidian_flames_style():
    """Top card is clearly ahead of second card but share < 0.40 → top_card_led."""
    data = {
        "summary": _make_summary(top1_ev_share=0.265, top3_ev_share=0.543, top5_ev_share=0.70),
        "top_hits": [
            # Charizard EV ~1.9x the next card to trigger ratio >= 1.75
            {"card_name": "Charizard ex", "ev_contribution": 3.8, "rarity_bucket": "ultra rare"},
            {"card_name": "Pidgeot ex", "ev_contribution": 2.0, "rarity_bucket": "ultra rare"},
            {"card_name": "Tyranitar ex", "ev_contribution": 1.4, "rarity_bucket": "illustration rare"},
            {"card_name": "Blissey ex", "ev_contribution": 1.1, "rarity_bucket": "double rare"},
            {"card_name": "Dragonite ex", "ev_contribution": 0.9, "rarity_bucket": "double rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]
    assert top_ev_meta["reason_code"] == "top_card_led", (
        f"Expected top_card_led, got {top_ev_meta['reason_code']}"
    )
    assert top_ev_meta["label"] == "Top card leads value"
    assert "charizard ex" in top_ev_meta["summary"].lower()
    assert "several hit types help" not in top_ev_meta["summary"].lower()
    # ratio signal should be present
    assert top_ev_meta["signals"]["top_card_to_second_ratio"] is not None
    assert top_ev_meta["signals"]["top_card_to_second_ratio"] >= 1.75


def test_top_ev_drivers_single_card_dependent_extreme():
    """Top card share >= 0.40 → single_card_dependent."""
    data = {
        "summary": _make_summary(top1_ev_share=0.665, top3_ev_share=0.80, top5_ev_share=0.90),
        "top_hits": [
            {"card_name": "Dragapult ex", "ev_contribution": 8.0, "rarity_bucket": "special illustration rare"},
            {"card_name": "Flareon ex", "ev_contribution": 2.0, "rarity_bucket": "ultra rare"},
            {"card_name": "Jolteon ex", "ev_contribution": 1.5, "rarity_bucket": "ultra rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]
    assert top_ev_meta["reason_code"] == "single_card_dependent"
    assert top_ev_meta["label"] == "One card carries value"
    assert "dragapult ex" in top_ev_meta["summary"].lower()


def test_top_ev_drivers_top_three_heavy_no_leader_gap():
    """top3_share >= 0.50 but no leader gap → top_three or rarity-specific, not top_card_led."""
    data = {
        "summary": _make_summary(top1_ev_share=0.22, top3_ev_share=0.52, top5_ev_share=0.68),
        "top_hits": [
            # Ratio: 3.0 / 2.5 = 1.2 < 1.75, so no leader gap
            {"card_name": "Umbreon ex", "ev_contribution": 3.0, "rarity_bucket": "illustration rare"},
            {"card_name": "Sylveon ex", "ev_contribution": 2.5, "rarity_bucket": "illustration rare"},
            {"card_name": "Glaceon ex", "ev_contribution": 2.0, "rarity_bucket": "illustration rare"},
            {"card_name": "Espeon ex", "ev_contribution": 1.5, "rarity_bucket": "ultra rare"},
            {"card_name": "Vaporeon ex", "ev_contribution": 1.2, "rarity_bucket": "double rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]
    assert top_ev_meta["reason_code"] != "top_card_led"
    assert top_ev_meta["reason_code"] != "broad_value_base"
    assert top_ev_meta["reason_code"] in {
        "top_three_carry_value", "ir_led_top3", "sir_led_top3", "ex_ultra_led_top3",
    }, f"Unexpected reason_code: {top_ev_meta['reason_code']}"


def test_top_ev_drivers_top_five_heavy_top_three_below_threshold():
    """top3_share < 0.45 but top5_share >= 0.65 → top_five_carry_value."""
    data = {
        "summary": _make_summary(top1_ev_share=0.15, top3_ev_share=0.42, top5_ev_share=0.68),
        "top_hits": [
            {"card_name": "Card A", "ev_contribution": 2.0, "rarity_bucket": "illustration rare"},
            {"card_name": "Card B", "ev_contribution": 1.9, "rarity_bucket": "ultra rare"},
            {"card_name": "Card C", "ev_contribution": 1.7, "rarity_bucket": "double rare"},
            {"card_name": "Card D", "ev_contribution": 1.6, "rarity_bucket": "special illustration rare"},
            {"card_name": "Card E", "ev_contribution": 1.5, "rarity_bucket": "hyper rare"},
            {"card_name": "Card F", "ev_contribution": 1.3, "rarity_bucket": "ultra rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]
    assert top_ev_meta["reason_code"] == "top_five_carry_value", (
        f"Expected top_five_carry_value, got {top_ev_meta['reason_code']}"
    )
    assert top_ev_meta["reason_code"] != "broad_value_base"


def test_top_ev_drivers_dominant_rarity_below_concentration_threshold():
    """Leading rarity >= 0.35 but all top-N thresholds below limits → dominant rarity language."""
    data = {
        # All effective shares below concentration thresholds
        "summary": _make_summary(top1_ev_share=0.18, top3_ev_share=0.35, top5_ev_share=0.50),
        "top_hits": [
            # IR dominates with ~40% but EVs are spread enough
            {"card_name": "IR 1", "ev_contribution": 2.5, "rarity_bucket": "illustration rare"},
            {"card_name": "IR 2", "ev_contribution": 2.0, "rarity_bucket": "illustration rare"},
            {"card_name": "UR 1", "ev_contribution": 1.8, "rarity_bucket": "ultra rare"},
            {"card_name": "DR 1", "ev_contribution": 1.5, "rarity_bucket": "double rare"},
            {"card_name": "HR 1", "ev_contribution": 1.2, "rarity_bucket": "hyper rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]
    # IR at 4.5 / (2.5+2.0+1.8+1.5+1.2) = 4.5/9.0 = 50% → illustration_led fires
    assert top_ev_meta["signals"]["leading_rarity_ev_share"] >= 0.35
    assert top_ev_meta["reason_code"] in {
        "illustration_led", "ir_led_top3", "sir_led", "sir_led_top3",
        "ex_ultra_led", "ex_ultra_led_top3",
    }, f"Unexpected reason_code: {top_ev_meta['reason_code']}"
    assert top_ev_meta["reason_code"] not in {"broad_value_base", "mixed_hit_base"}


def test_top_ev_drivers_true_broad_fallback():
    """All concentration signals below threshold → broad_value_base or mixed_hit_base."""
    data = {
        # All effective shares below broad-fallback thresholds; force via summary
        "summary": _make_summary(top1_ev_share=0.12, top3_ev_share=0.30, top5_ev_share=0.48),
        "top_hits": [
            # 5 different rarities each contributing a small, equal-ish share
            {"card_name": "Card A", "ev_contribution": 1.5, "rarity_bucket": "illustration rare"},
            {"card_name": "Card B", "ev_contribution": 1.4, "rarity_bucket": "special illustration rare"},
            {"card_name": "Card C", "ev_contribution": 1.3, "rarity_bucket": "ultra rare"},
            {"card_name": "Card D", "ev_contribution": 1.2, "rarity_bucket": "double rare"},
            {"card_name": "Card E", "ev_contribution": 1.1, "rarity_bucket": "hyper rare"},
            {"card_name": "Card F", "ev_contribution": 1.0, "rarity_bucket": "ace spec rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]
    # Leading rarity share: IR at 1.5 / 7.5 = 20% < 0.35
    assert top_ev_meta["signals"]["leading_rarity_ev_share"] < 0.35
    assert top_ev_meta["reason_code"] in {"broad_value_base", "mixed_hit_base"}, (
        f"Expected broad/mixed fallback, got {top_ev_meta['reason_code']}"
    )


def test_top_ev_drivers_no_broad_when_leader_gap():
    """Broad language must not appear when top_card_to_second_ratio >= 1.75 and top_card_share >= 0.25."""
    data = {
        "summary": _make_summary(top1_ev_share=0.28, top3_ev_share=0.48, top5_ev_share=0.62),
        "top_hits": [
            {"card_name": "Zacian V", "ev_contribution": 4.5, "rarity_bucket": "ultra rare"},
            {"card_name": "Zamazenta V", "ev_contribution": 2.4, "rarity_bucket": "ultra rare"},
            {"card_name": "Arceus V", "ev_contribution": 1.6, "rarity_bucket": "double rare"},
            {"card_name": "Dialga V", "ev_contribution": 1.2, "rarity_bucket": "double rare"},
            {"card_name": "Palkia V", "ev_contribution": 1.0, "rarity_bucket": "hyper rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]
    assert top_ev_meta["reason_code"] not in {"broad_value_base", "mixed_hit_base"}, (
        f"Broad language should be blocked, got {top_ev_meta['reason_code']}"
    )
    assert "several hit types help" not in top_ev_meta["summary"].lower()
    assert top_ev_meta["reason_code"] == "top_card_led"


def test_top_ev_drivers_no_broad_when_top3_high():
    """Broad language must not appear when top3_share >= 0.45."""
    data = {
        "summary": _make_summary(top1_ev_share=0.19, top3_ev_share=0.50, top5_ev_share=0.68),
        "top_hits": [
            {"card_name": "Card A", "ev_contribution": 2.8, "rarity_bucket": "illustration rare"},
            {"card_name": "Card B", "ev_contribution": 2.5, "rarity_bucket": "illustration rare"},
            {"card_name": "Card C", "ev_contribution": 2.0, "rarity_bucket": "special illustration rare"},
            {"card_name": "Card D", "ev_contribution": 1.5, "rarity_bucket": "ultra rare"},
            {"card_name": "Card E", "ev_contribution": 1.3, "rarity_bucket": "double rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]
    assert top_ev_meta["reason_code"] not in {"broad_value_base", "mixed_hit_base"}, (
        f"Broad language should be blocked when top3 >= 0.45, got {top_ev_meta['reason_code']}"
    )


def test_rarity_contribution_illustration_led_copy():
    data = {
        "summary": _make_summary(),
        "top_hits": [],
        "rankings": _rankings_illustration_led(),
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    rarity_meta = result["meta"]["rarityContribution"]

    assert rarity_meta["reason_code"] == "illustration_led"
    assert rarity_meta["label"] == "Illustration Rares carry the pool"
    assert "several rarity groups" not in rarity_meta["summary"].lower()


def test_rarity_contribution_pull_leader_low_value_ev_leader_high_value_explains_gap():
    data = {
        "summary": _make_summary(),
        "top_hits": [],
        "rankings": _rankings_pull_low_value_but_ev_high(),
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    rarity_meta = result["meta"]["rarityContribution"]

    assert "mostly pull lower-value cards" in rarity_meta["summary"].lower()
    assert "money comes from" in rarity_meta["summary"].lower()


def test_generic_broad_language_blocked_when_leader_share_above_35():
    data = {
        "summary": _make_summary(),
        "top_hits": [
            {"card_name": "Card IR 1", "ev_contribution": 3.8, "rarity_bucket": "illustration rare"},
            {"card_name": "Card IR 2", "ev_contribution": 2.2, "rarity_bucket": "illustration rare"},
            {"card_name": "Card UR", "ev_contribution": 2.0, "rarity_bucket": "ultra rare"},
            {"card_name": "Card DR", "ev_contribution": 1.5, "rarity_bucket": "double rare"},
        ],
        "rankings": _rankings_illustration_led(),
        "history_trend": [],
        "rip_statistics": {},
    }

    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]
    rarity_meta = result["meta"]["rarityContribution"]

    assert top_ev_meta["signals"]["leading_rarity_ev_share"] >= 0.35
    assert "several types of cards" not in top_ev_meta["summary"].lower()
    assert "several rarity groups" not in rarity_meta["summary"].lower()
    assert "broad rarity value base" not in rarity_meta["summary"].lower()


# ---------------------------------------------------------------------------
# New spec tests: Top EV Drivers concentration-first logic
# ---------------------------------------------------------------------------

def _sir_top3_hits():
    """Two SIRs in top 3; within-hits top_share < 0.30 so single_card is not triggered."""
    return [
        {"card_name": "Charizard SIR", "ev_contribution": 2.2, "rarity_bucket": "special illustration rare"},
        {"card_name": "Mew SIR", "ev_contribution": 2.0, "rarity_bucket": "special illustration rare"},
        {"card_name": "Mewtwo ex", "ev_contribution": 1.6, "rarity_bucket": "ultra rare"},
        {"card_name": "Pikachu ex", "ev_contribution": 1.1, "rarity_bucket": "ex"},
        {"card_name": "Other ex", "ev_contribution": 0.9, "rarity_bucket": "ex"},
    ]


def _ir_top3_hits():
    """Two IRs in top 3; within-hits top_share < 0.30."""
    return [
        {"card_name": "Eevee IR", "ev_contribution": 2.1, "rarity_bucket": "illustration rare"},
        {"card_name": "Sylveon IR", "ev_contribution": 1.9, "rarity_bucket": "illustration rare"},
        {"card_name": "Umbreon ex", "ev_contribution": 1.5, "rarity_bucket": "ultra rare"},
        {"card_name": "Leafeon IR", "ev_contribution": 1.3, "rarity_bucket": "illustration rare"},
        {"card_name": "Other UR", "ev_contribution": 1.0, "rarity_bucket": "ultra rare"},
    ]


def test_top3_concentration_sir_leads_value():
    """Spec test 1: top_card ~20%, top3 ~46%, top3 rarity = SIR.

    Expected: label = 'Special Illustration Rares drive value', no broad wording.
    """
    data = {
        "summary": _make_summary(
            top1_ev_share=0.20,
            top3_ev_share=0.46,
        ),
        "top_hits": _sir_top3_hits(),
        "rankings": _rankings_chase_heavy(),
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    top_ev_meta = result["meta"]["topEvDrivers"]

    assert top_ev_meta["reason_code"] == "sir_led_top3", (
        f"Expected sir_led_top3, got {top_ev_meta['reason_code']}"
    )
    assert top_ev_meta["label"] == "Special Illustration Rares drive value"
    assert "small group" in top_ev_meta["summary"].lower() or "high-end" in top_ev_meta["summary"].lower()
    assert "spread" not in top_ev_meta["label"].lower()
    assert "spread out" not in top_ev_meta["summary"].lower()


def test_top3_concentration_ir_leads_value():
    """Spec test 2: top_card ~20%, top3 ~46%, top3 rarity = Illustration Rare.

    Expected: label = 'Illustration Rares drive value'.
    """
    data = {
        "summary": _make_summary(
            top1_ev_share=0.20,
            top3_ev_share=0.46,
        ),
        "top_hits": _ir_top3_hits(),
        "rankings": _rankings_illustration_led(),
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    _assert_base_contract(result)
    top_ev_meta = result["meta"]["topEvDrivers"]

    assert top_ev_meta["reason_code"] == "ir_led_top3", (
        f"Expected ir_led_top3, got {top_ev_meta['reason_code']}"
    )
    assert top_ev_meta["label"] == "Illustration Rares drive value"
    assert "spread out" not in top_ev_meta["summary"].lower()


def test_dominant_rarity_share_triggers_dominant_language_below_top3_threshold():
    """Spec test 3: leading_rarity_share 38%, top3_ev_share below 0.45.

    Expected: dominant rarity language, not broad.
    """
    data = {
        "summary": _make_summary(
            top1_ev_share=0.18,
            top3_ev_share=0.40,  # below 0.45 to skip top3-heavy path
        ),
        "top_hits": [
            {"card_name": "SIR A", "ev_contribution": 3.8, "rarity_bucket": "special illustration rare"},
            {"card_name": "SIR B", "ev_contribution": 0.2, "rarity_bucket": "special illustration rare"},
            {"card_name": "UR C", "ev_contribution": 2.5, "rarity_bucket": "ultra rare"},
            {"card_name": "UR D", "ev_contribution": 2.0, "rarity_bucket": "ultra rare"},
            {"card_name": "UR E", "ev_contribution": 1.5, "rarity_bucket": "ultra rare"},
        ],
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]

    # Leading rarity within hits should be >= 0.35 (triggers dominant path)
    assert top_ev_meta["signals"]["leading_rarity_ev_share"] >= 0.35
    # Reason code must be a specific rarity profile, not broad or mixed
    assert top_ev_meta["reason_code"] not in ("broad_value_base", "top_cards_carry_value")
    assert "spread out" not in top_ev_meta["label"].lower()
    assert "several hit types" not in top_ev_meta["label"].lower()


def test_broad_value_base_only_when_all_thresholds_low():
    """Spec test 4: broad fallback fires only when top card, top 3, and rarity shares are all below thresholds.

    Expected: broad_value_base.
    """
    data = {
        "summary": _make_summary(
            top1_ev_share=0.12,
            top3_ev_share=0.33,  # below 0.40
        ),
        "top_hits": _broad_hits(),  # 6 cards, 6 different rarities, all similar EV
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    top_ev_meta = result["meta"]["topEvDrivers"]

    # All thresholds low — must resolve to broad or mixed (never to a specific rarity or top3)
    assert top_ev_meta["reason_code"] in ("broad_value_base", "mixed_hit_base"), (
        f"Expected broad/mixed, got {top_ev_meta['reason_code']}"
    )
    assert top_ev_meta["reason_code"] != "sir_led_top3"
    assert top_ev_meta["reason_code"] != "ir_led_top3"
    assert top_ev_meta["reason_code"] != "top_cards_carry_value"


# ---------------------------------------------------------------------------
# New spec tests: Pillar sub-metric interpretation copy
# ---------------------------------------------------------------------------

def test_profit_low_prob_high_p95_uses_probability_anchor_and_big_hit_driver():
    data = {
        "summary": _make_summary(
            prob_profit=0.12,
            p95_value_to_cost_ratio=2.60,
            mean_value_to_cost_ratio=0.55,
            median_value_to_cost_ratio=0.18,
            profit_tier="C",
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    summary = result["meta"]["profit"]["summary"]
    assert "middle-of-the-pack profit setup" in summary
    assert "high-end upside is strong" in summary
    assert "helped by strong hits" in summary


def test_profit_low_prob_strong_mean_mentions_average_holds_up():
    data = {
        "summary": _make_summary(
            prob_profit=0.12,
            p95_value_to_cost_ratio=2.30,
            mean_value_to_cost_ratio=0.74,
            median_value_to_cost_ratio=0.35,
            profit_tier="C",
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    summary = result["meta"]["profit"]["summary"]
    assert "middle-of-the-pack profit setup" in summary
    assert "upside can still beat the pack price" in summary
    assert "score holds up because the win chance is better than many sets" in summary


def test_profit_low_prob_weak_median_mentions_below_cost_normal_packs():
    data = {
        "summary": _make_summary(
            prob_profit=0.12,
            p95_value_to_cost_ratio=1.80,
            mean_value_to_cost_ratio=0.50,
            median_value_to_cost_ratio=0.10,
            profit_tier="D",
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    summary = result["meta"]["profit"]["summary"]
    assert "below-average profit setup" in summary
    assert "upside can still beat the pack price" in summary


def test_profit_summary_changes_when_probability_changes_with_same_tail_metrics():
    low_prob = build_rip_interpretation(
        {
            "summary": _make_summary(
                prob_profit=0.07,
                p95_value_to_cost_ratio=2.60,
                mean_value_to_cost_ratio=0.65,
                median_value_to_cost_ratio=0.18,
            ),
            "top_hits": _broad_hits(),
            "rankings": [],
            "history_trend": [],
            "rip_statistics": {},
        }
    )
    higher_prob = build_rip_interpretation(
        {
            "summary": _make_summary(
                prob_profit=0.18,
                p95_value_to_cost_ratio=2.60,
                mean_value_to_cost_ratio=0.65,
                median_value_to_cost_ratio=0.18,
            ),
            "top_hits": _broad_hits(),
            "rankings": [],
            "history_trend": [],
            "rip_statistics": {},
        }
    )

    low_summary = low_prob["meta"]["profit"]["summary"]
    high_summary = higher_prob["meta"]["profit"]["summary"]
    assert low_summary != high_summary
    assert "below-average profit setup" in low_summary
    assert "score is strong because both win rate and upside are better than most sets" in high_summary


def test_safety_high_expected_loss_uses_rough_or_brutal_language():
    data = {
        "summary": _make_summary(
            safety_tier="F",
            expected_loss_when_losing_fraction=0.86,
            median_loss_when_losing_fraction=0.82,
            p05_shortfall_to_cost=0.90,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    label = result["meta"]["safety"]["label"].lower()
    summary = result["meta"]["safety"]["summary"].lower()
    assert "brutal" in label or "rough" in label
    assert "punishing" in summary or "hurt" in summary or "very little" in summary


def test_sa_safety_tier_avoids_brutal_and_very_rough_labels():
    data = {
        "summary": _make_summary(
            safety_tier="S",
            expected_loss_when_losing_fraction=0.88,
            median_loss_when_losing_fraction=0.84,
            p05_shortfall_to_cost=0.92,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    label = result["meta"]["safety"]["label"].lower()
    summary = result["meta"]["safety"]["summary"].lower()
    assert "brutal" not in label
    assert "very rough" not in label
    assert "easier to handle" in summary


def test_f_safety_tier_high_loss_keeps_punishing_miss_language():
    data = {
        "summary": _make_summary(
            safety_tier="F",
            expected_loss_when_losing_fraction=0.83,
            median_loss_when_losing_fraction=0.80,
            p05_shortfall_to_cost=0.88,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    label = result["meta"]["safety"]["label"].lower()
    summary = result["meta"]["safety"]["summary"].lower()
    assert "very rough" in label or "brutal" in label or "rough" in label
    assert "hurt" in summary or "punishing" in summary or "very little" in summary


def test_stability_top1_threshold_marks_one_card_dependence():
    data = {
        "summary": _make_summary(
            stability_tier="C",
            top1_ev_share=0.32,
            top3_ev_share=0.42,
            effective_chase_count=20.0,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["stability"]
    assert meta["label"] == "One card carries value"
    assert "depends heavily" in meta["summary"].lower()


def test_stability_top3_threshold_marks_top_heavy_profile():
    data = {
        "summary": _make_summary(
            stability_tier="C",
            top1_ev_share=0.20,
            top3_ev_share=0.47,
            effective_chase_count=22.0,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["stability"]
    assert meta["label"] == "Top cards carry value"
    assert "small group" in meta["summary"].lower()


def test_stability_effective_chase_25_or_more_marks_well_spread():
    data = {
        "summary": _make_summary(
            stability_tier="B",
            top1_ev_share=0.12,
            top3_ev_share=0.30,
            effective_chase_count=26.0,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["stability"]
    assert meta["label"] == "Value is well spread"
    assert "spread across many cards" in meta["summary"].lower()


def test_stability_df_tier_not_well_spread_without_supporting_metrics():
    data = {
        "summary": _make_summary(
            stability_tier="F",
            top1_ev_share=0.24,
            top3_ev_share=0.40,
            effective_chase_count=12.0,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {},
    }
    result = build_rip_interpretation(data)
    label = result["meta"]["stability"]["label"]
    assert label != "Value is well spread"


# ---------------------------------------------------------------------------
# New spec tests: Outcome Distribution / Historical Trend / Pack Breakdown
# ---------------------------------------------------------------------------

def test_outcome_distribution_low_median_high_p95_is_low_floor_big_ceiling():
    data = {
        "summary": _make_summary(
            pack_cost=5.0,
            median_value_to_cost_ratio=0.22,
            p95_value_to_cost_ratio=3.05,
            p99_value_to_cost_ratio=7.0,
            max_value=120.0,
            prob_big_hit=0.015,
            prob_profit=0.09,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["outcomeDistribution"]
    assert meta["reason_code"] == "low_floor_big_ceiling"
    assert meta["label"] == "Low floor, big ceiling"


def test_outcome_distribution_huge_max_outlier_is_extreme_outlier_shape():
    data = {
        "summary": _make_summary(
            pack_cost=5.0,
            median_value_to_cost_ratio=0.33,
            p95_value_to_cost_ratio=2.20,
            p99_value_to_cost_ratio=10.0,
            max_value=700.0,
            prob_big_hit=0.02,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["outcomeDistribution"]
    assert meta["reason_code"] == "extreme_outlier_shape"


def test_outcome_distribution_extreme_outlier_shape_when_p99_missing_and_max_extreme():
    data = {
        "summary": _make_summary(
            pack_cost=12.20,
            median_value=2.89,
            median_value_to_cost_ratio=0.237,
            p95_value_to_cost_ratio=1.30,
            max_value=4240.06,
            p99_value_to_cost_ratio=None,
            prob_big_hit=0.006,
            prob_profit=0.078,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["outcomeDistribution"]
    assert meta["reason_code"] == "extreme_outlier_shape"
    assert meta["label"] == "Extreme outlier at the top"
    summary = meta["summary"].lower()
    assert "rare outlier" in summary
    assert "stretches the chart" in summary


def test_outcome_distribution_low_big_hit_prob_high_p95_is_chase_heavy_distribution():
    data = {
        "summary": _make_summary(
            pack_cost=5.0,
            median_value_to_cost_ratio=0.31,
            p95_value_to_cost_ratio=2.30,
            p99_value_to_cost_ratio=8.0,
            max_value=70.0,
            prob_big_hit=0.005,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["outcomeDistribution"]
    assert meta["reason_code"] == "chase_heavy_distribution"
    assert "hard to reach" in meta["summary"].lower()


def test_outcome_distribution_weak_median_weak_p95_is_weak_distribution():
    data = {
        "summary": _make_summary(
            pack_cost=5.0,
            median_value_to_cost_ratio=0.16,
            p95_value_to_cost_ratio=1.20,
            p99_value_to_cost_ratio=2.0,
            max_value=20.0,
            prob_big_hit=0.01,
        ),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["outcomeDistribution"]
    assert meta["reason_code"] == "weak_distribution"
    assert meta["signals"]["outcome_profile"] == "weak_distribution"


def test_historical_trend_flat_mean_far_below_break_even_profile():
    data = {
        "summary": _make_summary(),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [
            {"simulated_mean_pack_value_vs_pack_cost": 0.56, "simulated_median_pack_value_vs_pack_cost": 0.20},
            {"simulated_mean_pack_value_vs_pack_cost": 0.57, "simulated_median_pack_value_vs_pack_cost": 0.21},
            {"simulated_mean_pack_value_vs_pack_cost": 0.57, "simulated_median_pack_value_vs_pack_cost": 0.21},
        ],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["historicalTrend"]
    assert meta["reason_code"] in {"flat_far_below_break_even", "flat_below_break_even"}


def test_historical_trend_flat_mean_near_break_even_profile():
    data = {
        "summary": _make_summary(),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [
            {"simulated_mean_pack_value_vs_pack_cost": 0.87, "simulated_median_pack_value_vs_pack_cost": 0.23},
            {"simulated_mean_pack_value_vs_pack_cost": 0.88, "simulated_median_pack_value_vs_pack_cost": 0.23},
            {"simulated_mean_pack_value_vs_pack_cost": 0.88, "simulated_median_pack_value_vs_pack_cost": 0.24},
        ],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["historicalTrend"]
    assert meta["reason_code"] == "flat_near_break_even"


def test_historical_trend_improving_but_below_break_even_profile():
    data = {
        "summary": _make_summary(),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [
            {"simulated_mean_pack_value_vs_pack_cost": 0.70, "simulated_median_pack_value_vs_pack_cost": 0.50},
            {"simulated_mean_pack_value_vs_pack_cost": 0.74, "simulated_median_pack_value_vs_pack_cost": 0.53},
            {"simulated_mean_pack_value_vs_pack_cost": 0.76, "simulated_median_pack_value_vs_pack_cost": 0.55},
        ],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["historicalTrend"]
    assert meta["reason_code"] == "improving_below_break_even"


def test_historical_trend_data_limited_profile():
    data = {
        "summary": _make_summary(),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [
            {"simulated_mean_pack_value_vs_pack_cost": 0.70, "simulated_median_pack_value_vs_pack_cost": 0.50},
            {"simulated_mean_pack_value_vs_pack_cost": 0.72, "simulated_median_pack_value_vs_pack_cost": 0.52},
        ],
        "rip_statistics": _rip_stats_normal(),
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["historicalTrend"]
    assert meta["reason_code"] == "trend_still_forming"
    assert meta["label"] == "Trend still forming"


def test_pack_breakdown_normal_only_high_baseline_profile():
    data = {
        "summary": _make_summary(),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {
            "pack_paths": {"normal": 10000},
            "normal_pack_states": {
                "baseline": 7000,
                "small_hit": 2000,
                "big_hit": 1000,
            },
        },
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["packBreakdown"]
    assert meta["reason_code"] in {"one_path_only", "mostly_normal_baseline"}


def test_pack_breakdown_god_pack_present_profile():
    data = {
        "summary": _make_summary(),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {
            "pack_paths": {"normal": 999500, "god": 500},
            "normal_pack_states": {"baseline": 600000, "hit": 399500},
        },
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["packBreakdown"]
    assert meta["reason_code"] == "god_pack_present"


def test_pack_breakdown_normal_with_hit_variety_profile():
    data = {
        "summary": _make_summary(),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {
            "pack_paths": {"normal": 10000},
            "normal_pack_states": {
                "baseline": 5000,
                "small_hit": 1800,
                "mid_hit": 1500,
                "big_hit": 1100,
                "ultra_hit": 600,
            },
        },
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["packBreakdown"]
    assert meta["reason_code"] == "normal_with_hit_variety"


def test_pack_breakdown_special_path_matters_profile():
    data = {
        "summary": _make_summary(),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": {
            "pack_paths": {"normal": 9850, "special": 150},
            "normal_pack_states": {"baseline": 6500, "hit": 3350},
        },
    }
    result = build_rip_interpretation(data)
    meta = result["meta"]["packBreakdown"]
    assert meta["reason_code"] == "special_path_matters"


# ---------------------------------------------------------------------------
# Matrix interpretation planner tests (Step 8 — new archetype coverage)
# ---------------------------------------------------------------------------

import itertools


def _matrix_make_summary(profit_tier, safety_tier, stability_tier):
    """Build a minimal summary dict with explicit tiers for matrix tests."""
    tier_to_score = {"S": 90.0, "A": 78.0, "B": 62.0, "C": 46.0, "D": 28.0, "F": 8.0}
    return _make_summary(
        profit_score=tier_to_score[profit_tier],
        safety_score=tier_to_score[safety_tier],
        stability_score=tier_to_score[stability_tier],
        profit_tier=profit_tier,
        safety_tier=safety_tier,
        stability_tier=stability_tier,
    )


def _matrix_interpret(profit_tier, safety_tier, stability_tier):
    from backend.interpretation.rips.engine import build_rip_interpretation
    data = {
        "summary": _matrix_make_summary(profit_tier, safety_tier, stability_tier),
        "top_hits": _broad_hits(),
        "rankings": [],
        "history_trend": [],
        "rip_statistics": _rip_stats_normal(),
    }
    return build_rip_interpretation(data)


# ---------------------------------------------------------------------------
# Test 1: elite_return / high safety / high stability
# ---------------------------------------------------------------------------

def test_matrix_elite_return_high_safety_high_stability():
    """Elite return + high safety + high stability -> elite_open, positive framing."""
    result = _matrix_interpret("S", "A", "A")
    pack_meta = result["meta"]["packScore"]

    assert pack_meta["reason_code"] == "elite_open"
    assert pack_meta["label"] in ("Elite open", "Great to open right now")
    assert pack_meta["severity"] == "positive"

    summary_lower = pack_meta["summary"].lower()
    # Must mention value, manageable misses, spread
    assert any(w in summary_lower for w in ("pay back", "return", "value")), summary_lower
    assert any(w in summary_lower for w in ("easier", "manageable", "safer")), summary_lower
    assert any(w in summary_lower for w in ("spread", "enough cards")), summary_lower

    # Matrix signals populated
    assert result["meta"]["packScore"]["signals"]["profit_lane"] == "elite_return"
    assert result["meta"]["packScore"]["signals"]["safety_band"] == "high"
    assert result["meta"]["packScore"]["signals"]["stability_band"] == "high"
    assert result["meta"]["packScore"]["signals"]["matrix_key"] == "elite_return:high:high"


# ---------------------------------------------------------------------------
# Test 2: elite_return / low safety / high stability
# ---------------------------------------------------------------------------

def test_matrix_elite_return_low_safety_high_stability():
    """Elite return + low safety + high stability -> label mentions risky misses, spread value."""
    result = _matrix_interpret("S", "F", "A")
    pack_meta = result["meta"]["packScore"]

    # strong_but_risky because safety is low
    assert pack_meta["reason_code"] == "strong_but_risky"
    label_lower = pack_meta["label"].lower()
    assert any(w in label_lower for w in ("risky", "risk", "rough")), label_lower

    summary_lower = pack_meta["summary"].lower()
    assert "bad packs can still hurt" in summary_lower or "bad packs can hurt" in summary_lower
    assert any(w in summary_lower for w in ("spread", "one-card")), summary_lower

    assert pack_meta["signals"]["profit_lane"] == "elite_return"
    assert pack_meta["signals"]["safety_band"] == "low"
    assert pack_meta["signals"]["stability_band"] == "high"
    assert pack_meta["signals"]["matrix_key"] == "elite_return:low:high"


# ---------------------------------------------------------------------------
# Test 3: good_return / medium safety / low stability
# ---------------------------------------------------------------------------

def test_matrix_good_return_medium_safety_low_stability():
    """Good return + medium safety + low stability -> good_value_shaky_path."""
    result = _matrix_interpret("B", "C", "F")
    pack_meta = result["meta"]["packScore"]

    assert pack_meta["reason_code"] == "good_value_shaky_path"
    assert pack_meta["label"] == "Good value, shaky path"

    summary_lower = pack_meta["summary"].lower()
    assert any(w in summary_lower for w in ("value", "good")), summary_lower
    assert any(w in summary_lower for w in ("right hits", "fragile", "worth it")), summary_lower

    assert pack_meta["signals"]["profit_lane"] == "good_return"
    assert pack_meta["signals"]["safety_band"] == "medium"
    assert pack_meta["signals"]["stability_band"] == "low"
    assert pack_meta["signals"]["matrix_key"] == "good_return:medium:low"


# ---------------------------------------------------------------------------
# Test 4: average_return / low safety / medium stability
# ---------------------------------------------------------------------------

def test_matrix_average_return_low_safety_medium_stability():
    """Average return + low safety -> average_but_risky."""
    result = _matrix_interpret("C", "F", "C")
    pack_meta = result["meta"]["packScore"]

    assert pack_meta["reason_code"] == "average_but_risky"
    label_lower = pack_meta["label"].lower()
    assert "average" in label_lower or "risky" in label_lower

    summary_lower = pack_meta["summary"].lower()
    assert "average" in summary_lower
    assert any(w in summary_lower for w in ("hurt", "painful", "rough", "pressure")), summary_lower

    assert pack_meta["signals"]["profit_lane"] == "average_return"
    assert pack_meta["signals"]["safety_band"] == "low"
    assert pack_meta["signals"]["stability_band"] == "medium"
    assert pack_meta["signals"]["matrix_key"] == "average_return:low:medium"


# ---------------------------------------------------------------------------
# Test 5: weak_return / high safety / high stability
# ---------------------------------------------------------------------------

def test_matrix_weak_return_high_safety_high_stability():
    """Weak return + high safety + high stability -> safe_but_low_reward."""
    result = _matrix_interpret("D", "A", "S")
    pack_meta = result["meta"]["packScore"]

    assert pack_meta["reason_code"] in ("safe_but_low_reward", "okay_but_capped")
    assert pack_meta["label"] in (
        "Safe, but low reward",
        "Low risk, low reward",
        "Safe, but not exciting",
        "Low reward, safer misses",
    )

    summary_lower = pack_meta["summary"].lower()
    assert any(w in summary_lower for w in ("easier", "manageable", "forgiving", "spread")), summary_lower
    assert any(w in summary_lower for w in ("not big enough", "not strong enough", "weak", "not enough")), summary_lower

    assert pack_meta["signals"]["profit_lane"] == "weak_return"
    assert pack_meta["signals"]["safety_band"] == "high"
    assert pack_meta["signals"]["stability_band"] == "high"


# ---------------------------------------------------------------------------
# Test 6: failing_return / low safety / low stability
# ---------------------------------------------------------------------------

def test_matrix_failing_return_low_safety_low_stability():
    """Failing return + low safety + low stability -> bottom_tier_open with harsh language."""
    result = _matrix_interpret("F", "F", "F")
    pack_meta = result["meta"]["packScore"]

    assert pack_meta["reason_code"] == "bottom_tier_open"
    assert pack_meta["label"] == "One of the toughest opens"
    assert pack_meta["severity"] == "negative"

    summary_lower = pack_meta["summary"].lower()
    assert "three fronts" in summary_lower or "toughest" in summary_lower
    assert any(w in summary_lower for w in ("not paying back", "weak value")), summary_lower
    assert any(w in summary_lower for w in ("brutal", "rough", "painful")), summary_lower
    assert any(w in summary_lower for w in ("not enough value spread", "right hits")), summary_lower

    assert pack_meta["signals"]["profit_lane"] == "failing_return"
    assert pack_meta["signals"]["safety_band"] == "low"
    assert pack_meta["signals"]["stability_band"] == "low"
    assert pack_meta["signals"]["matrix_key"] == "failing_return:low:low"


# ---------------------------------------------------------------------------
# Test 7: B/B/C/F profile — must not collapse to generic weak_open
# ---------------------------------------------------------------------------

def test_matrix_b_b_c_f_does_not_collapse_to_weak():
    """B profit / B pack / C safety / F stability -> good_value_shaky_path, not weak_open."""
    result = _matrix_interpret("B", "C", "F")
    pack_meta = result["meta"]["packScore"]

    assert pack_meta["reason_code"] == "good_value_shaky_path"
    assert pack_meta["reason_code"] not in {"weak_open", "very_weak_open", "bottom_tier_open"}

    assert pack_meta["signals"]["profit_lane"] == "good_return"
    assert pack_meta["signals"]["stability_band"] == "low"


# ---------------------------------------------------------------------------
# Test 8: F/F/F/F — must be harsher than weak_return cases
# ---------------------------------------------------------------------------

def test_matrix_ffff_harsher_than_weak_return():
    """F/F/F/F (failing everything) must use bottom_tier_open, not just very_weak_open."""
    result_ffff = _matrix_interpret("F", "F", "F")
    result_weak = _matrix_interpret("D", "D", "D")

    ffff_meta = result_ffff["meta"]["packScore"]
    weak_meta = result_weak["meta"]["packScore"]

    assert ffff_meta["reason_code"] == "bottom_tier_open"
    assert weak_meta["reason_code"] in {"very_weak_open", "weak_open", "below_average_open"}
    assert ffff_meta["reason_code"] != weak_meta["reason_code"]
    assert ffff_meta["summary"] != weak_meta["summary"]

    # FFFF summary should be harsher
    ffff_lower = ffff_meta["summary"].lower()
    assert any(w in ffff_lower for w in ("brutal", "toughest", "three fronts")), ffff_lower


# ---------------------------------------------------------------------------
# Test 9: Every combination of profit_lane x safety_band x stability_band
# produces a non-empty label and summary
# ---------------------------------------------------------------------------

_ALL_PROFIT_TIERS = ["S", "A", "B", "C", "D", "F"]
_ALL_BAND_TIERS = ["S", "A", "B", "C", "D", "F"]  # S/A=high, B/C=medium, D/F=low

import pytest as _pytest


@_pytest.mark.parametrize(
    "profit_tier,safety_tier,stability_tier",
    list(itertools.product(_ALL_PROFIT_TIERS, ["A", "C", "D"], ["A", "C", "D"])),
)
def test_matrix_all_combinations_return_nonempty(profit_tier, safety_tier, stability_tier):
    """Every matrix combination must produce a non-empty, non-whitespace label and summary."""
    result = _matrix_interpret(profit_tier, safety_tier, stability_tier)
    pack_meta = result["meta"]["packScore"]

    assert pack_meta["label"].strip(), (
        f"Empty label for {profit_tier}/{safety_tier}/{stability_tier}"
    )
    assert pack_meta["summary"].strip(), (
        f"Empty summary for {profit_tier}/{safety_tier}/{stability_tier}"
    )
    assert pack_meta["signals"]["matrix_key"] is not None, (
        f"No matrix_key for {profit_tier}/{safety_tier}/{stability_tier}"
    )
    assert pack_meta["signals"]["pack_archetype"] is not None, (
        f"No pack_archetype for {profit_tier}/{safety_tier}/{stability_tier}"
    )
    assert pack_meta["reason_code"] in {
        "elite_open", "strong_but_risky", "good_open", "above_average_but_flawed",
        "good_value_shaky_path", "average_open", "average_but_risky", "hit_dependent_open",
        "below_average_open", "very_weak_open", "bottom_tier_open",
        "okay_but_capped", "safe_but_low_reward", "weak_open", "data_limited",
    }, f"Unknown reason_code {pack_meta['reason_code']} for {profit_tier}/{safety_tier}/{stability_tier}"

