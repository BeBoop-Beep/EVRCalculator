"""Project 6.2 slot-schema simulation math validation.

These probabilities are test-only and do not represent researched pull rates.
"""

import math
import random
from statistics import fmean

import pandas as pd
import pytest

import backend.simulations.evrSimulator as evr_simulator_module
from backend.constants.tcg.pokemon.megaEvolutionEra.megaEvolution import SetMegaEvolutionConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.paldeaEvolved import SetPaldeaEvolvedConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.simulations.evrSimulator import PackEVRSimulator, _should_use_monte_carlo_v2, get_simulation_engine
from backend.simulations.slotSchemaSimulator import simulate_slot_schema_packs as simulate_slot_schema_packs_real


TEST_ONLY_PROBABILITY_NOTE = "These probabilities are test-only and do not represent researched pull rates."


def _build_test_only_rare_slot_probability(non_rare_weights):
    total_non_rare = sum(float(weight) for weight in non_rare_weights.values())
    rare_residual = 1.0 - total_non_rare
    if rare_residual <= 0:
        raise ValueError("test-only table requires positive residual for rare.")
    table = {"rare": rare_residual}
    table.update(non_rare_weights)
    return table


TEST_ONLY_CHILLING_REIGN_RARE_SLOT_PROBABILITY = _build_test_only_rare_slot_probability(
    {
        "holo rare": 0.15,
        "regular v": 0.14,
        "regular vmax": 0.10,
        "full art v": 0.08,
        "full art trainer": 0.07,
        "alternate art v": 0.05,
        "alternate art vmax": 0.04,
        "rainbow trainer": 0.04,
        "rainbow vmax": 0.03,
        "gold secret rare": 0.02,
    }
)


TEST_ONLY_EVOLVING_SKIES_RARE_SLOT_PROBABILITY = _build_test_only_rare_slot_probability(
    {
        "holo rare": 0.16,
        "regular v": 0.13,
        "regular vmax": 0.11,
        "full art v": 0.08,
        "full art trainer": 0.06,
        "alternate art v": 0.05,
        "alternate art vmax": 0.04,
        "rainbow trainer": 0.04,
        "rainbow vmax": 0.03,
        "gold secret rare": 0.02,
    }
)


class TestOnlyChillingReignRuntimeConfig(SetChillingReignConfig):
    SLOT_SCHEMA_RUNTIME_ENABLED = True
    RARE_SLOT_PROBABILITY = TEST_ONLY_CHILLING_REIGN_RARE_SLOT_PROBABILITY
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1.0,
        },
    }

    @classmethod
    def get_rarity_pack_multiplier(cls):
        return {"common": 5, "uncommon": 3}


class TestOnlyEvolvingSkiesRuntimeConfig(SetEvolvingSkiesConfig):
    SLOT_SCHEMA_RUNTIME_ENABLED = True
    RARE_SLOT_PROBABILITY = TEST_ONLY_EVOLVING_SKIES_RARE_SLOT_PROBABILITY
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1.0,
        },
    }

    @classmethod
    def get_rarity_pack_multiplier(cls):
        return {"common": 5, "uncommon": 3}


class DraftChillingReignRuntimeConfig(SetChillingReignConfig):
    SLOT_SCHEMA_RUNTIME_ENABLED = True
    RARE_SLOT_PROBABILITY = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT

    @classmethod
    def get_rarity_pack_multiplier(cls):
        return {"common": 5, "uncommon": 3}


class DraftEvolvingSkiesRuntimeConfig(SetEvolvingSkiesConfig):
    SLOT_SCHEMA_RUNTIME_ENABLED = True
    RARE_SLOT_PROBABILITY = SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT

    @classmethod
    def get_rarity_pack_multiplier(cls):
        return {"common": 5, "uncommon": 3}


def _with_alias_columns(rows):
    normalized_rows = []
    for row in rows:
        enriched = dict(row)
        enriched["Card Name"] = row["name"]
        enriched["Rarity"] = row["rarity"]
        normalized_rows.append(enriched)
    return pd.DataFrame(normalized_rows)


def _build_chilling_reign_variant_level_df():
    rows = [
        {
            "name": "Common Regular Alpha",
            "rarity": "Common",
            "printing_type": "non-holo",
            "card_number": "1",
            "Price ($)": 0.10,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Uncommon Regular Beta",
            "rarity": "Uncommon",
            "printing_type": "non-holo",
            "card_number": "40",
            "Price ($)": 0.20,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Common Reverse Spark",
            "rarity": "Common",
            "printing_type": "reverse-holo",
            "card_number": "2",
            "Price ($)": 0.15,
            "Reverse Variant Price ($)": 0.35,
        },
        {
            "name": "Uncommon Reverse Spark",
            "rarity": "Uncommon",
            "printing_type": "reverse-holo",
            "card_number": "41",
            "Price ($)": 0.25,
            "Reverse Variant Price ($)": 0.45,
        },
        {
            "name": "Dual Variant Rare",
            "rarity": "Rare",
            "printing_type": "non-holo",
            "card_number": "70",
            "Price ($)": 1.10,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Dual Variant Rare",
            "rarity": "Rare",
            "printing_type": "reverse-holo",
            "card_number": "70",
            "Price ($)": 1.05,
            "Reverse Variant Price ($)": 1.25,
        },
        {
            "name": "Rare Non-Holo Anchor",
            "rarity": "Rare",
            "printing_type": "non-holo",
            "card_number": "71",
            "Price ($)": 1.30,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Rare Reverse-Only Anchor",
            "rarity": "Rare",
            "printing_type": "reverse-holo",
            "card_number": "72",
            "Price ($)": 1.15,
            "Reverse Variant Price ($)": 1.05,
        },
        {
            "name": "Holo Rare Anchor",
            "rarity": "Holo Rare",
            "printing_type": "holo",
            "card_number": "90",
            "Price ($)": 2.40,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Holo Rare Reverse Mirror",
            "rarity": "Holo Rare",
            "printing_type": "reverse-holo",
            "card_number": "91",
            "Price ($)": 2.10,
            "Reverse Variant Price ($)": 2.60,
        },
        {
            "name": "Frostwing V",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "120",
            "Price ($)": 4.50,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Frostwing VMAX",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "140",
            "Price ($)": 6.40,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Frostwing V (Full Art)",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "170",
            "Price ($)": 8.10,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Professor Borealis",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "190",
            "Price ($)": 7.25,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Frostwing V (Alternate Full Art)",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "173",
            "Price ($)": 16.00,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Frostwing VMAX Alternate Art Secret",
            "rarity": "Secret Rare",
            "printing_type": "holo",
            "card_number": "201",
            "Price ($)": 21.00,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Professor Borealis Rainbow",
            "rarity": "Secret Rare",
            "printing_type": "holo",
            "card_number": "215",
            "Price ($)": 12.00,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Frostwing VMAX",
            "rarity": "Secret Rare",
            "printing_type": "holo",
            "card_number": "205",
            "Price ($)": 14.00,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Golden Glacier Orb",
            "rarity": "Secret Rare",
            "printing_type": "holo",
            "card_number": "225",
            "Price ($)": 18.00,
            "Reverse Variant Price ($)": None,
        },
    ]
    return _with_alias_columns(rows)


def _build_evolving_skies_variant_level_df():
    rows = [
        {
            "name": "Common Regular Alpha",
            "rarity": "Common",
            "printing_type": "non-holo",
            "card_number": "1",
            "Price ($)": 0.11,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Uncommon Regular Beta",
            "rarity": "Uncommon",
            "printing_type": "non-holo",
            "card_number": "40",
            "Price ($)": 0.22,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Common Reverse Spark",
            "rarity": "Common",
            "printing_type": "reverse-holo",
            "card_number": "2",
            "Price ($)": 0.16,
            "Reverse Variant Price ($)": 0.36,
        },
        {
            "name": "Uncommon Reverse Spark",
            "rarity": "Uncommon",
            "printing_type": "reverse-holo",
            "card_number": "41",
            "Price ($)": 0.26,
            "Reverse Variant Price ($)": 0.46,
        },
        {
            "name": "Dual Variant Rare",
            "rarity": "Rare",
            "printing_type": "non-holo",
            "card_number": "70",
            "Price ($)": 1.20,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Dual Variant Rare",
            "rarity": "Rare",
            "printing_type": "reverse-holo",
            "card_number": "70",
            "Price ($)": 1.12,
            "Reverse Variant Price ($)": 1.28,
        },
        {
            "name": "Rare Non-Holo Anchor",
            "rarity": "Rare",
            "printing_type": "non-holo",
            "card_number": "71",
            "Price ($)": 1.42,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Rare Reverse-Only Anchor",
            "rarity": "Rare",
            "printing_type": "reverse-holo",
            "card_number": "72",
            "Price ($)": 1.18,
            "Reverse Variant Price ($)": 1.08,
        },
        {
            "name": "Holo Rare Anchor",
            "rarity": "Holo Rare",
            "printing_type": "holo",
            "card_number": "90",
            "Price ($)": 2.55,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Holo Rare Reverse Mirror",
            "rarity": "Holo Rare",
            "printing_type": "reverse-holo",
            "card_number": "91",
            "Price ($)": 2.15,
            "Reverse Variant Price ($)": 2.65,
        },
        {
            "name": "Skywing V",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "94",
            "Price ($)": 4.70,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Skywing VMAX",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "95",
            "Price ($)": 6.75,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Skywing V (Full Art)",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "179",
            "Price ($)": 8.35,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Professor Nimbus",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "200",
            "Price ($)": 7.40,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Skywing V (Alternate Full Art)",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "188",
            "Price ($)": 16.50,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Skywing VMAX Alternate Art Secret",
            "rarity": "Secret Rare",
            "printing_type": "holo",
            "card_number": "215",
            "Price ($)": 21.50,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Professor Nimbus Rainbow",
            "rarity": "Secret Rare",
            "printing_type": "holo",
            "card_number": "223",
            "Price ($)": 12.25,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Skywing VMAX",
            "rarity": "Secret Rare",
            "printing_type": "holo",
            "card_number": "214",
            "Price ($)": 14.25,
            "Reverse Variant Price ($)": None,
        },
        {
            "name": "Golden Horizon Orb",
            "rarity": "Secret Rare",
            "printing_type": "holo",
            "card_number": "234",
            "Price ($)": 18.50,
            "Reverse Variant Price ($)": None,
        },
    ]
    return _with_alias_columns(rows)


def _resolve_card_pool_key(outcome):
    if outcome == "regular reverse":
        return "reverse"
    return outcome


def _mean_pool_value(card_pool, outcome):
    pool_key = _resolve_card_pool_key(outcome)
    pool = card_pool[pool_key]
    return fmean(float(row["value"]) for row in pool)


def calculate_expected_slot_schema_ev_from_pools(config, card_pool):
    pack_structure = config.PACK_STRUCTURE

    common_ev = pack_structure["common_slots"] * _mean_pool_value(card_pool, "common")
    uncommon_ev = pack_structure["uncommon_slots"] * _mean_pool_value(card_pool, "uncommon")

    reverse_ev = 0.0
    for slot_name, slot_weights in config.REVERSE_SLOT_PROBABILITIES.items():
        for outcome, probability in slot_weights.items():
            reverse_ev += float(probability) * _mean_pool_value(card_pool, outcome)

    rare_slot_ev = 0.0
    for outcome, probability in config.RARE_SLOT_PROBABILITY.items():
        rare_slot_ev += float(probability) * _mean_pool_value(card_pool, outcome)

    total_ev = common_ev + uncommon_ev + reverse_ev + rare_slot_ev
    return {
        "expected_common_ev": common_ev,
        "expected_uncommon_ev": uncommon_ev,
        "expected_reverse_ev": reverse_ev,
        "expected_rare_slot_ev": rare_slot_ev,
        "expected_total_pack_ev": total_ev,
    }


def _capture_runtime_card_pool(config, simulation_input_df, monkeypatch):
    capture = {}

    def _capture_only(_config, card_pool, num_packs):
        capture["num_packs"] = num_packs
        capture["card_pool"] = card_pool
        return {
            "packs": [],
            "values": [0.0],
            "rarity_pull_counts": {},
            "rarity_value_totals": {},
            "mean": 0.0,
            "std_dev": 0.0,
            "min": 0.0,
            "max": 0.0,
            "distribution": [0.0],
        }

    monkeypatch.setattr(evr_simulator_module, "simulate_slot_schema_packs", _capture_only)
    PackEVRSimulator(config).calculate_evr_simulations(simulation_input_df)
    return capture["card_pool"]


def _run_bounded_seeded_runtime_simulation(config, simulation_input_df, monkeypatch, *, num_packs, seed):
    capture = {}
    bounded_pack_count = num_packs

    def _bounded_sim(_config, card_pool, num_packs=None, **_kwargs):
        runtime_num_packs = num_packs
        assert runtime_num_packs == 1000000
        capture["card_pool"] = card_pool
        return simulate_slot_schema_packs_real(
            _config,
            card_pool,
            num_packs=bounded_pack_count,
            rng=random.Random(seed),
        )

    monkeypatch.setattr(evr_simulator_module, "simulate_slot_schema_packs", _bounded_sim)
    simulator = PackEVRSimulator(config)
    simulation_results = simulator.calculate_evr_simulations(simulation_input_df)
    return simulation_results["sim_results"], capture["card_pool"], simulator


@pytest.mark.parametrize(
    "runtime_config,input_builder",
    [
        (TestOnlyChillingReignRuntimeConfig, _build_chilling_reign_variant_level_df),
        (TestOnlyEvolvingSkiesRuntimeConfig, _build_evolving_skies_variant_level_df),
    ],
)
def test_test_only_probability_tables_cover_all_mapped_outcomes(runtime_config, input_builder):
    del input_builder

    probability_keys = set(runtime_config.RARE_SLOT_PROBABILITY.keys())
    mapped_keys = set(runtime_config.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())

    assert probability_keys.issubset(mapped_keys)
    assert sum(runtime_config.RARE_SLOT_PROBABILITY.values()) == pytest.approx(1.0)
    assert runtime_config.RARE_SLOT_PROBABILITY["rare"] > 0.0

    required_outcomes = {
        "rare",
        "holo rare",
        "regular v",
        "regular vmax",
        "full art v",
        "alternate art v",
        "rainbow vmax",
        "gold secret rare",
    }
    assert required_outcomes.issubset(probability_keys)
    assert TEST_ONLY_PROBABILITY_NOTE in __doc__


def test_production_guardrails_remain_inert_and_sv_mega_behavior_is_unchanged():
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
    "draft_table,config_cls",
    [
        (SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT, SetChillingReignConfig),
        (SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT, SetEvolvingSkiesConfig),
    ],
)
def test_draft_empirical_tables_match_mapping_keys_and_residual_rare_is_valid(draft_table, config_cls):
    mapping_keys = set(config_cls.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())
    assert set(draft_table.keys()) == mapping_keys
    assert draft_table["rare"] >= 0.0
    assert sum(draft_table.values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "runtime_config,input_builder",
    [
        (DraftChillingReignRuntimeConfig, _build_chilling_reign_variant_level_df),
        (DraftEvolvingSkiesRuntimeConfig, _build_evolving_skies_variant_level_df),
    ],
)
def test_draft_empirical_tables_run_bounded_ev_math_validation_harness(runtime_config, input_builder, monkeypatch):
    simulation_input_df = input_builder()
    sim_results, card_pool, simulator = _run_bounded_seeded_runtime_simulation(
        runtime_config,
        simulation_input_df,
        monkeypatch,
        num_packs=12000,
        seed=66026,
    )

    ev_breakdown = calculate_expected_slot_schema_ev_from_pools(runtime_config, card_pool)
    simulated_mean_ev = float(sim_results["mean"])
    expected_total_ev = ev_breakdown["expected_total_pack_ev"]

    assert abs(simulated_mean_ev - expected_total_ev) <= max(0.2, 0.04 * expected_total_ev)

    rarity_counts = sim_results["rarity_pull_counts"]
    assert rarity_counts["regular reverse"] == 12000
    assert rarity_counts["common"] == 12000 * runtime_config.PACK_STRUCTURE["common_slots"]
    assert rarity_counts["uncommon"] == 12000 * runtime_config.PACK_STRUCTURE["uncommon_slots"]

    rare_slot_draws = sum(rarity_counts.get(outcome, 0) for outcome in runtime_config.RARE_SLOT_PROBABILITY)
    assert rare_slot_draws == 12000

    metrics = simulator.calculate_pack_metrics(sim_results, pack_price=4.99)
    assert "total_ev" in metrics
    assert "opening_pack_roi" in metrics
    assert "net_value" in metrics


@pytest.mark.parametrize(
    "runtime_config,input_builder",
    [
        (TestOnlyChillingReignRuntimeConfig, _build_chilling_reign_variant_level_df),
        (TestOnlyEvolvingSkiesRuntimeConfig, _build_evolving_skies_variant_level_df),
    ],
)
def test_variant_level_slot_pool_construction_and_separation(runtime_config, input_builder, monkeypatch):
    simulation_input_df = input_builder()
    card_pool = _capture_runtime_card_pool(runtime_config, simulation_input_df, monkeypatch)

    required_outcomes = set(runtime_config.RARE_SLOT_PROBABILITY.keys())
    assert required_outcomes.issubset(card_pool.keys())
    for outcome in required_outcomes:
        assert len(card_pool[outcome]) > 0, outcome

    reverse_pool = card_pool["reverse"]
    assert len(reverse_pool) > 0

    reverse_names = {row["Card Name"] for row in reverse_pool}
    rare_names = {row["Card Name"] for row in card_pool["rare"]}

    assert "Dual Variant Rare" in rare_names
    assert "Dual Variant Rare" in reverse_names

    dual_in_rare = [row for row in card_pool["rare"] if row["Card Name"] == "Dual Variant Rare"]
    dual_in_reverse = [row for row in reverse_pool if row["Card Name"] == "Dual Variant Rare"]

    assert len(dual_in_rare) == 1
    assert dual_in_rare[0]["printing_type"] == "non-holo"
    assert len(dual_in_reverse) >= 1
    assert all(row["printing_type"] == "reverse-holo" for row in dual_in_reverse)

    assert "Common Reverse Spark" in reverse_names
    assert "Uncommon Reverse Spark" in reverse_names
    assert "Rare Non-Holo Anchor" not in reverse_names

    # Reverse slot rows must use reverse value field, not base price.
    for row in reverse_pool:
        assert float(row["value"]) == pytest.approx(float(row["Reverse Variant Price ($)"]))

    # Outcome-specific spot checks prove mapped pool construction by card_number/name/rarity filters.
    assert {row["printing_type"] for row in card_pool["rare"]} == {"non-holo"}
    assert {row["printing_type"] for row in card_pool["holo rare"]} == {"holo"}
    assert {row["Card Name"] for row in card_pool["regular v"]} == {
        name for name in {"Frostwing V", "Skywing V"} if any(r["Card Name"] == name for r in card_pool["regular v"])
    }
    assert {row["Card Name"] for row in card_pool["regular vmax"]} == {
        name for name in {"Frostwing VMAX", "Skywing VMAX"} if any(r["Card Name"] == name for r in card_pool["regular vmax"])
    }


@pytest.mark.parametrize(
    "runtime_config,input_builder",
    [
        (TestOnlyChillingReignRuntimeConfig, _build_chilling_reign_variant_level_df),
        (TestOnlyEvolvingSkiesRuntimeConfig, _build_evolving_skies_variant_level_df),
    ],
)
def test_hand_calculated_ev_matches_bounded_seeded_simulation_and_frequency_targets(
    runtime_config,
    input_builder,
    monkeypatch,
):
    simulation_input_df = input_builder()
    sim_results, card_pool, simulator = _run_bounded_seeded_runtime_simulation(
        runtime_config,
        simulation_input_df,
        monkeypatch,
        num_packs=30000,
        seed=62026,
    )

    ev_breakdown = calculate_expected_slot_schema_ev_from_pools(runtime_config, card_pool)
    expected_total_ev = ev_breakdown["expected_total_pack_ev"]
    simulated_mean_ev = float(sim_results["mean"])

    ev_delta = abs(simulated_mean_ev - expected_total_ev)
    ev_tolerance = max(0.15, 0.03 * expected_total_ev)
    assert ev_delta <= ev_tolerance, (
        f"expected_total_pack_ev={expected_total_ev:.6f} simulated_mean={simulated_mean_ev:.6f} "
        f"delta={ev_delta:.6f} tolerance={ev_tolerance:.6f} breakdown={ev_breakdown}"
    )

    rarity_counts = sim_results["rarity_pull_counts"]
    rarity_value_totals = sim_results["rarity_value_totals"]

    assert rarity_counts["common"] == 30000 * runtime_config.PACK_STRUCTURE["common_slots"]
    assert rarity_counts["uncommon"] == 30000 * runtime_config.PACK_STRUCTURE["uncommon_slots"]
    assert rarity_counts["regular reverse"] == 30000

    rare_slot_draws = sum(rarity_counts.get(outcome, 0) for outcome in runtime_config.RARE_SLOT_PROBABILITY)
    assert rare_slot_draws == 30000

    # Bucket label guardrails: simulator uses normalized bucket names, not raw DB labels.
    assert "Ultra Rare" not in rarity_counts
    assert "Secret Rare" not in rarity_counts

    for outcome, expected_probability in runtime_config.RARE_SLOT_PROBABILITY.items():
        observed_probability = rarity_counts.get(outcome, 0) / rare_slot_draws
        statistical_tolerance = max(
            0.01,
            5.0 * math.sqrt(expected_probability * (1.0 - expected_probability) / rare_slot_draws),
        )
        assert abs(observed_probability - expected_probability) <= statistical_tolerance, (
            f"outcome={outcome!r} observed={observed_probability:.6f} "
            f"expected={expected_probability:.6f} tolerance={statistical_tolerance:.6f}"
        )

    # Value totals should be coherent with sampled counts and simulated values.
    for outcome, count in rarity_counts.items():
        if count == 0:
            continue
        assert outcome in rarity_value_totals
        sampled_avg = rarity_value_totals[outcome] / count
        if outcome in card_pool:
            pool_values = [float(row["value"]) for row in card_pool[outcome]]
        elif outcome == "regular reverse":
            pool_values = [float(row["value"]) for row in card_pool["reverse"]]
        else:
            continue
        epsilon = 1e-9
        assert (min(pool_values) - epsilon) <= sampled_avg <= (max(pool_values) + epsilon)

    assert sum(float(v) for v in rarity_value_totals.values()) == pytest.approx(sum(sim_results["values"]))

    pack_metrics = simulator.calculate_pack_metrics(sim_results, pack_price=4.99)
    assert "total_ev" in pack_metrics
    assert "opening_pack_roi" in pack_metrics
    assert "net_value" in pack_metrics
