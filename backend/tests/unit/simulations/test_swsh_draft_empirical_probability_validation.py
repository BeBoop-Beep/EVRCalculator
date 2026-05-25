"""Project 6.7 draft empirical simulation validation for SWSH sets.

This suite validates draft empirical rare-slot probability tables for
Chilling Reign and Evolving Skies with bounded simulation checks while
ensuring production runtime remains intentionally enabled only for
swsh6/swsh7 under controlled best-available empirical promotion.
"""

from statistics import median

import pytest

from backend.constants.tcg.pokemon.megaEvolutionEra.megaEvolution import SetMegaEvolutionConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.paldeaEvolved import SetPaldeaEvolvedConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.scripts.audit_swsh_slot_schema_readiness import (
    SetConfigMeta,
    _analyze_set_rows,
    _extract_complete_bucket_classification_audit,
)
from backend.simulations.evrSimulator import _should_use_monte_carlo_v2, get_simulation_engine
from backend.tests.unit.simulations.test_slot_schema_simulation_math_validation import (
    _build_chilling_reign_variant_level_df,
    _build_evolving_skies_variant_level_df,
    _capture_runtime_card_pool,
    _run_bounded_seeded_runtime_simulation,
    calculate_expected_slot_schema_ev_from_pools,
)


class DraftEmpiricalChillingReignRuntimeConfig(SetChillingReignConfig):
    SLOT_SCHEMA_RUNTIME_ENABLED = True
    RARE_SLOT_PROBABILITY = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT

    @classmethod
    def get_rarity_pack_multiplier(cls):
        return {"common": 5, "uncommon": 3}


class DraftEmpiricalEvolvingSkiesRuntimeConfig(SetEvolvingSkiesConfig):
    SLOT_SCHEMA_RUNTIME_ENABLED = True
    RARE_SLOT_PROBABILITY = SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT

    @classmethod
    def get_rarity_pack_multiplier(cls):
        return {"common": 5, "uncommon": 3}


def _make_meta_from_config(config_cls, set_key):
    source_confidence = getattr(config_cls, "SLOT_SCHEMA_SOURCE_CONFIDENCE", {})
    if not isinstance(source_confidence, dict):
        source_confidence = {}

    reverse_table = getattr(config_cls, "REVERSE_SLOT_PROBABILITIES", None)
    reverse_shape = "missing"
    if isinstance(reverse_table, dict):
        reverse_shape = f"slots={','.join(sorted(str(k) for k in reverse_table.keys()))}"

    return SetConfigMeta(
        set_key=set_key,
        class_name=config_cls.__name__,
        set_name=str(getattr(config_cls, "SET_NAME", set_key)),
        set_id=str(getattr(config_cls, "SET_ID", "")),
        printed_total=getattr(config_cls, "PRINTED_TOTAL", None),
        total=getattr(config_cls, "TOTAL", None),
        simulation_engine=str(getattr(config_cls, "SIMULATION_ENGINE", "v2")),
        slot_schema_runtime_enabled=bool(getattr(config_cls, "SLOT_SCHEMA_RUNTIME_ENABLED", False)),
        has_rare_slot_probability=hasattr(config_cls, "RARE_SLOT_PROBABILITY"),
        has_reverse_slot_probabilities=isinstance(reverse_table, dict),
        reverse_slot_probability_shape=reverse_shape,
        standard_pack_shape=True,
        pack_shape_reason="standard",
        source_confidence_status=str(source_confidence.get("status", "")),
        source_confidence_runtime_ready=(
            bool(source_confidence["runtime_ready"]) if "runtime_ready" in source_confidence else None
        ),
        source_confidence_probability_ready=(
            bool(source_confidence["rare_slot_probability_ready"])
            if "rare_slot_probability_ready" in source_confidence
            else None
        ),
    )


def _pack_value_smoke(values, pack_price):
    mean_value = sum(values) / len(values)
    return {
        "mean": mean_value,
        "median": float(median(values)),
        "prob_profit": float(sum(value > pack_price for value in values) / len(values)),
        "pack_count": len(values),
    }


@pytest.mark.parametrize(
    "config_cls,draft_attr",
    [
        (SetChillingReignConfig, "CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT"),
        (SetEvolvingSkiesConfig, "EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT"),
    ],
)
def test_project_67_preconditions_hold_before_runtime_simulation(config_cls, draft_attr):
    draft_table = getattr(config_cls, draft_attr)
    mapping_keys = set(config_cls.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())

    assert config_cls.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert hasattr(config_cls, "RARE_SLOT_PROBABILITY")
    assert config_cls.RARE_SLOT_PROBABILITY == draft_table

    assert isinstance(draft_table, dict)
    assert set(draft_table.keys()) == mapping_keys
    assert sum(draft_table.values()) == pytest.approx(1.0)
    assert draft_table["rare"] >= 0.0


def test_project_67_draft_tables_do_not_include_parent_or_named_card_keys():
    forbidden_parent_keys = {
        "Ultra Rare",
        "Secret Rare",
        "Full Art",
        "Rainbow",
        "VMAX",
    }
    forbidden_named_card_keys = {
        "Umbreon VMAX Alternate Art Secret",
        "Gold Snorlax",
        "Blaziken VMAX Alt",
    }

    for draft_table in (
        SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT,
        SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT,
    ):
        assert forbidden_parent_keys.isdisjoint(draft_table.keys())
        assert forbidden_named_card_keys.isdisjoint(draft_table.keys())


@pytest.mark.parametrize(
    "runtime_config,input_builder,num_packs,seed",
    [
        (DraftEmpiricalChillingReignRuntimeConfig, _build_chilling_reign_variant_level_df, 20000, 67061),
        (DraftEmpiricalEvolvingSkiesRuntimeConfig, _build_evolving_skies_variant_level_df, 20000, 67062),
    ],
)
def test_project_67_draft_empirical_slot_schema_simulation_validation(
    runtime_config,
    input_builder,
    num_packs,
    seed,
    monkeypatch,
):
    simulation_input_df = input_builder()
    sim_results, card_pool, simulator = _run_bounded_seeded_runtime_simulation(
        runtime_config,
        simulation_input_df,
        monkeypatch,
        num_packs=num_packs,
        seed=seed,
    )

    expected_breakdown = calculate_expected_slot_schema_ev_from_pools(runtime_config, card_pool)
    expected_ev = float(expected_breakdown["expected_total_pack_ev"])
    simulated_ev = float(sim_results["mean"])

    ev_abs_delta = abs(simulated_ev - expected_ev)
    ev_rel_delta = ev_abs_delta / expected_ev if expected_ev > 0 else 0.0

    assert ev_rel_delta < 0.02 or ev_abs_delta < 0.10, (
        f"expected={expected_ev:.6f} simulated={simulated_ev:.6f} "
        f"abs_delta={ev_abs_delta:.6f} rel_delta={ev_rel_delta:.6%}"
    )

    rarity_counts = sim_results["rarity_pull_counts"]
    assert rarity_counts["common"] == num_packs * runtime_config.PACK_STRUCTURE["common_slots"]
    assert rarity_counts["uncommon"] == num_packs * runtime_config.PACK_STRUCTURE["uncommon_slots"]
    assert rarity_counts["regular reverse"] == num_packs

    rare_slot_draws = sum(rarity_counts.get(bucket, 0) for bucket in runtime_config.RARE_SLOT_PROBABILITY)
    assert rare_slot_draws == num_packs

    largest_bucket_delta = 0.0
    for bucket, expected_probability in runtime_config.RARE_SLOT_PROBABILITY.items():
        observed_probability = rarity_counts.get(bucket, 0) / rare_slot_draws
        tolerance = max(0.01, expected_probability * 0.25)
        delta = abs(observed_probability - expected_probability)
        largest_bucket_delta = max(largest_bucket_delta, delta)
        assert delta <= tolerance, (
            f"bucket={bucket} observed={observed_probability:.6f} "
            f"expected={expected_probability:.6f} delta={delta:.6f} tolerance={tolerance:.6f}"
        )

    assert largest_bucket_delta <= 0.08

    pack_metrics = simulator.calculate_pack_metrics(sim_results, pack_price=4.99)
    assert isinstance(pack_metrics, dict)
    assert "total_ev" in pack_metrics
    assert "opening_pack_roi" in pack_metrics
    assert "net_value" in pack_metrics

    smoke_metrics = _pack_value_smoke(sim_results["values"], pack_price=4.99)
    assert "mean" in smoke_metrics
    assert "median" in smoke_metrics
    assert "prob_profit" in smoke_metrics
    assert smoke_metrics["pack_count"] == num_packs


@pytest.mark.parametrize(
    "runtime_config,input_builder",
    [
        (DraftEmpiricalChillingReignRuntimeConfig, _build_chilling_reign_variant_level_df),
        (DraftEmpiricalEvolvingSkiesRuntimeConfig, _build_evolving_skies_variant_level_df),
    ],
)
def test_project_67_reverse_holo_stays_reverse_slot_only(runtime_config, input_builder, monkeypatch):
    simulation_input_df = input_builder()
    card_pool = _capture_runtime_card_pool(runtime_config, simulation_input_df, monkeypatch)

    reverse_pool = card_pool["reverse"]
    assert reverse_pool
    assert all(row["printing_type"] == "reverse-holo" for row in reverse_pool)

    rare_or_better_buckets = [
        "rare",
        "holo rare",
        "regular v",
        "regular vmax",
        "full art v",
        "full art trainer",
        "alternate art v",
        "alternate art vmax",
        "rainbow trainer",
        "rainbow vmax",
        "gold secret rare",
    ]
    for bucket in rare_or_better_buckets:
        assert all(row["printing_type"] != "reverse-holo" for row in card_pool[bucket]), bucket

    assert {row["printing_type"] for row in card_pool["rare"]} == {"non-holo"}
    assert {row["printing_type"] for row in card_pool["holo rare"]} == {"holo"}

    assert card_pool["regular v"]
    assert card_pool["regular vmax"]
    assert card_pool["full art v"]
    assert card_pool["alternate art v"]
    assert card_pool["gold secret rare"]


def test_project_67_sv_mega_behavior_unchanged_and_production_safety_guards_hold():
    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert SetEvolvingSkiesConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY")
    assert hasattr(SetEvolvingSkiesConfig, "RARE_SLOT_PROBABILITY")
    assert SetChillingReignConfig.RARE_SLOT_PROBABILITY == SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT
    assert SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY == SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT

    assert _should_use_monte_carlo_v2(SetPaldeaEvolvedConfig) is True
    assert _should_use_monte_carlo_v2(SetMegaEvolutionConfig) is True
    assert get_simulation_engine(SetPaldeaEvolvedConfig) == "v2"
    assert get_simulation_engine(SetMegaEvolutionConfig) == "v2"


@pytest.mark.parametrize(
    "config_cls,set_key",
    [
        (SetChillingReignConfig, "chillingReign"),
        (SetEvolvingSkiesConfig, "evolvingSkies"),
    ],
)
def test_project_67_readiness_regression_reflects_intentional_runtime_enablement(config_cls, set_key):
    meta = _make_meta_from_config(config_cls, set_key)
    dedicated = _extract_complete_bucket_classification_audit(config_cls)

    assert dedicated is not None

    result = _analyze_set_rows(
        meta,
        "candidate_standard",
        "mainline Sword & Shield set id",
        cards=[],
        variants=[],
        market_rows=[],
        dedicated_bucket_audit=dedicated,
    )

    assert result["bucket_classification_status"] == "bucket_classification_ready"
    assert result["probability_readiness"] in {
        "probability_ready_candidate",
        "candidate_probability_model_possible",
    }
    assert result["slot_schema_runtime_enabled"] is True
    assert result["has_rare_slot_probability"] is True
    assert result["runtime_ready_candidate"] is False