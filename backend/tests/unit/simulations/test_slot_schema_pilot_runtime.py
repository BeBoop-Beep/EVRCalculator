import random

import pandas as pd
import pytest

import backend.simulations.evrSimulator as evr_simulator_module
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.simulations.evrSimulator import PackEVRSimulator, _should_use_monte_carlo_v2, get_simulation_engine
from backend.simulations.slotSchemaSimulator import simulate_slot_schema_packs as simulate_slot_schema_packs_real


class _ChillingReignRuntimeReadyConfig(SetChillingReignConfig):
    SLOT_SCHEMA_RUNTIME_ENABLED = True

    @classmethod
    def get_rarity_pack_multiplier(cls):
        return {"common": 5, "uncommon": 3}

    RARE_SLOT_PROBABILITY = {
        "rare": 1.0,
    }
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1.0,
        },
    }


def _build_tiny_card_groups_as_dataframes():
    common = pd.DataFrame(
        [
            {"Card Name": "Common A", "Price ($)": 0.10},
            {"Card Name": "Common B", "Price ($)": 0.12},
        ]
    )
    uncommon = pd.DataFrame(
        [
            {"Card Name": "Uncommon A", "Price ($)": 0.25},
            {"Card Name": "Uncommon B", "Price ($)": 0.30},
        ]
    )
    rare = pd.DataFrame(
        [
            {"Card Name": "Rare A", "Price ($)": 1.50},
            {"Card Name": "Rare B", "Price ($)": 2.00},
        ]
    )
    reverse = pd.DataFrame(
        [
            {"Card Name": "Reverse A", "Reverse Variant Price ($)": 0.75},
            {"Card Name": "Reverse B", "Reverse Variant Price ($)": 0.90},
        ]
    )
    hit = pd.DataFrame(
        [
            {"Card Name": "Hit A", "Price ($)": 8.0, "Rarity": "ultra rare"},
        ]
    )
    return {
        "common": common,
        "uncommon": uncommon,
        "rare": rare,
        "reverse": reverse,
        "hit": hit,
    }


def _build_tiny_slot_schema_input_df():
    return pd.DataFrame(
        [
            {
                "Card Name": "Rare A",
                "Rarity": "Rare",
                "printing_type": "non-holo",
                "card_number": "10",
                "Price ($)": 1.5,
                "Reverse Variant Price ($)": 0.0,
            },
            {
                "Card Name": "Holo Rare A",
                "Rarity": "Holo Rare",
                "printing_type": "holo",
                "card_number": "11",
                "Price ($)": 2.5,
                "Reverse Variant Price ($)": 0.0,
            },
            {
                "Card Name": "Rare Reverse",
                "Rarity": "Rare",
                "printing_type": "reverse-holo",
                "card_number": "12",
                "Price ($)": 1.0,
                "Reverse Variant Price ($)": 0.5,
            },
            {
                "Card Name": "Regular V",
                "Rarity": "Ultra Rare",
                "printing_type": "holo",
                "card_number": "120",
                "Price ($)": 6.0,
                "Reverse Variant Price ($)": 0.0,
            },
        ]
    )


def _build_tiny_slot_schema_input_df_without_holo_rare():
    df = _build_tiny_slot_schema_input_df()
    return df[df["Rarity"] != "Holo Rare"].copy()


def test_chilling_reign_pilot_uses_slot_schema_not_v2_shape():
    assert get_simulation_engine(SetChillingReignConfig) == "slot_schema"
    assert _should_use_monte_carlo_v2(SetChillingReignConfig) is False


def test_chilling_reign_slot_schema_runtime_is_disabled_until_real_probability_tables_exist():
    assert getattr(SetChillingReignConfig, "SLOT_SCHEMA_RUNTIME_ENABLED", True) is False


def test_runtime_enabled_config_missing_probability_tables_fails_readiness_guard():
    class _RuntimeEnabledWithoutProbabilityTables(SetChillingReignConfig):
        SLOT_SCHEMA_RUNTIME_ENABLED = True

        @classmethod
        def get_rarity_pack_multiplier(cls):
            return {"common": 5, "uncommon": 3}

        RARE_SLOT_PROBABILITY = {"rare": 1.0}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"regular reverse": 1.0},
        }

        PACK_STRUCTURE = {
            "common_slots": 5,
            "uncommon_slots": 3,
            "rare_family_slots": [
                {
                    "name": "rare_slot_1",
                    "role": "reverse_parallel",
                    "probability_attr": "REVERSE_SLOT_PROBABILITIES",
                    "probability_key": "slot_1",
                    "default_outcome": "regular reverse",
                },
                {
                    "name": "rare_slot_2",
                    "role": "rare_or_better",
                    "probability_attr": "RARE_SLOT_PROBABILITY",
                    "default_outcome": "rare",
                },
                {
                    "name": "rare_slot_3",
                    "role": "rare_or_better",
                    "probability_attr": "MISSING_RUNTIME_TABLE",
                    "default_outcome": "rare",
                },
            ],
        }

    with pytest.raises(ValueError, match="runtime readiness failed"):
        PackEVRSimulator(_RuntimeEnabledWithoutProbabilityTables).calculate_evr_simulations(pd.DataFrame())


def test_slot_schema_config_without_runtime_enabled_fails_at_calculate_evr_simulations(monkeypatch):
    class _NoRuntimeFlag(SetChillingReignConfig):
        SLOT_SCHEMA_RUNTIME_ENABLED = False

        @classmethod
        def get_rarity_pack_multiplier(cls):
            return {"common": 5, "uncommon": 3}

        RARE_SLOT_PROBABILITY = {"rare": 1.0}
        REVERSE_SLOT_PROBABILITIES = {"slot_1": {"regular reverse": 1.0}}

    monkeypatch.setattr(
        evr_simulator_module,
        "extract_scarletandviolet_card_groups",
        lambda _config, _df: _build_tiny_card_groups_as_dataframes(),
    )

    with pytest.raises(ValueError, match="SLOT_SCHEMA_RUNTIME_ENABLED"):
        PackEVRSimulator(_NoRuntimeFlag).calculate_evr_simulations(pd.DataFrame())


def test_chilling_reign_calculate_path_refuses_execution_while_runtime_disabled(monkeypatch):
    class _ChillingReignRuntimeDisabledConfig(SetChillingReignConfig):
        SLOT_SCHEMA_RUNTIME_ENABLED = False

        @classmethod
        def get_rarity_pack_multiplier(cls):
            return {"common": 5, "uncommon": 3}

        RARE_SLOT_PROBABILITY = {"rare": 1.0}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"regular reverse": 1.0},
        }

    monkeypatch.setattr(
        evr_simulator_module,
        "extract_scarletandviolet_card_groups",
        lambda _config, _df: _build_tiny_card_groups_as_dataframes(),
    )

    with pytest.raises(ValueError, match="SLOT_SCHEMA_RUNTIME_ENABLED"):
        PackEVRSimulator(_ChillingReignRuntimeDisabledConfig).calculate_evr_simulations(pd.DataFrame())


def test_chilling_reign_slot_schema_runtime_executes_with_tiny_dataframe_pools(monkeypatch):
    monkeypatch.setattr(
        evr_simulator_module,
        "extract_scarletandviolet_card_groups",
        lambda _config, _df: _build_tiny_card_groups_as_dataframes(),
    )

    def _bounded_slot_schema_sim(config, card_pool, num_packs):
        assert num_packs == 1000000
        return simulate_slot_schema_packs_real(config, card_pool, num_packs=8, rng=random.Random(12345))

    monkeypatch.setattr(evr_simulator_module, "simulate_slot_schema_packs", _bounded_slot_schema_sim)

    simulator = PackEVRSimulator(_ChillingReignRuntimeReadyConfig)
    simulation_results = simulator.calculate_evr_simulations(_build_tiny_slot_schema_input_df())

    sim_results = simulation_results["sim_results"]
    assert "values" in sim_results
    assert "mean" in sim_results
    assert "rarity_pull_counts" in sim_results
    assert "rarity_value_totals" in sim_results
    assert "distribution" in sim_results

    pack_metrics = simulator.calculate_pack_metrics(sim_results, pack_price=4.99)
    assert "total_ev" in pack_metrics
    assert "opening_pack_roi" in pack_metrics


def test_slot_schema_runtime_builds_outcome_pools_via_mapping(monkeypatch):
    class _RuntimeConfigWithHoloOutcome(SetChillingReignConfig):
        SLOT_SCHEMA_RUNTIME_ENABLED = True

        @classmethod
        def get_rarity_pack_multiplier(cls):
            return {"common": 5, "uncommon": 3}

        RARE_SLOT_PROBABILITY = {
            "rare": 0.2,
            "holo rare": 0.5,
            "regular v": 0.3,
        }
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {
                "regular reverse": 1.0,
            },
        }

    monkeypatch.setattr(
        evr_simulator_module,
        "extract_scarletandviolet_card_groups",
        lambda _config, _df: _build_tiny_card_groups_as_dataframes(),
    )

    def _assert_pool_and_return(_config, card_pool, num_packs):
        assert num_packs == 1000000
        assert sum(_RuntimeConfigWithHoloOutcome.RARE_SLOT_PROBABILITY.values()) == pytest.approx(1.0)

        assert "rare" in card_pool
        assert len(card_pool["rare"]) == 1
        assert card_pool["rare"][0]["Card Name"] == "Rare A"

        assert "holo rare" in card_pool
        assert len(card_pool["holo rare"]) == 1
        assert card_pool["holo rare"][0]["Card Name"] == "Holo Rare A"
        assert all(item["Card Name"] != "Rare Reverse" for item in card_pool["holo rare"])

        assert "regular v" in card_pool
        assert len(card_pool["regular v"]) == 1
        assert card_pool["regular v"][0]["Card Name"] == "Regular V"

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

    monkeypatch.setattr(evr_simulator_module, "simulate_slot_schema_packs", _assert_pool_and_return)

    simulator = PackEVRSimulator(_RuntimeConfigWithHoloOutcome)
    simulation_results = simulator.calculate_evr_simulations(_build_tiny_slot_schema_input_df())
    assert "sim_results" in simulation_results


def test_slot_schema_runtime_readiness_fails_when_required_outcome_is_missing_from_mapping():
    class _RuntimeConfigMissingMappedOutcome(SetChillingReignConfig):
        SLOT_SCHEMA_RUNTIME_ENABLED = True

        @classmethod
        def get_rarity_pack_multiplier(cls):
            return {"common": 5, "uncommon": 3}

        RARE_SLOT_PROBABILITY = {
            "rare": 0.5,
            "not-mapped": 0.5,
        }
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {
                "regular reverse": 1.0,
            },
        }

    with pytest.raises(ValueError, match="SLOT_SCHEMA_OUTCOME_POOL_MAPPING is missing outcomes"):
        PackEVRSimulator(_RuntimeConfigMissingMappedOutcome).calculate_evr_simulations(_build_tiny_slot_schema_input_df())


def test_slot_schema_runtime_pool_construction_fails_when_required_outcome_pool_is_empty(monkeypatch):
    class _RuntimeConfigWithRequiredHolo(SetChillingReignConfig):
        SLOT_SCHEMA_RUNTIME_ENABLED = True

        @classmethod
        def get_rarity_pack_multiplier(cls):
            return {"common": 5, "uncommon": 3}

        RARE_SLOT_PROBABILITY = {
            "rare": 0.0,
            "holo rare": 1.0,
        }
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {
                "regular reverse": 1.0,
            },
        }

    monkeypatch.setattr(
        evr_simulator_module,
        "extract_scarletandviolet_card_groups",
        lambda _config, _df: _build_tiny_card_groups_as_dataframes(),
    )

    with pytest.raises(ValueError, match="required outcome 'holo rare' resolved to an empty mapped pool"):
        PackEVRSimulator(_RuntimeConfigWithRequiredHolo).calculate_evr_simulations(
            _build_tiny_slot_schema_input_df_without_holo_rare()
        )


def test_slot_schema_runtime_allows_empty_optional_mapped_outcomes_not_in_rare_slot_probability(monkeypatch):
    class _RuntimeConfigRareOnly(SetChillingReignConfig):
        SLOT_SCHEMA_RUNTIME_ENABLED = True

        @classmethod
        def get_rarity_pack_multiplier(cls):
            return {"common": 5, "uncommon": 3}

        RARE_SLOT_PROBABILITY = {
            "rare": 1.0,
        }
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {
                "regular reverse": 1.0,
            },
        }

    monkeypatch.setattr(
        evr_simulator_module,
        "extract_scarletandviolet_card_groups",
        lambda _config, _df: _build_tiny_card_groups_as_dataframes(),
    )

    def _assert_pool_and_return(_config, card_pool, num_packs):
        assert num_packs == 1000000
        assert "rare" in card_pool
        assert len(card_pool["rare"]) == 1
        # Not required by RARE_SLOT_PROBABILITY, so empty optional pools may be omitted.
        assert "holo rare" not in card_pool
        # Optional outcomes may still be present when their mapped pool is non-empty.
        assert "regular v" in card_pool
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

    monkeypatch.setattr(evr_simulator_module, "simulate_slot_schema_packs", _assert_pool_and_return)

    simulation_results = PackEVRSimulator(_RuntimeConfigRareOnly).calculate_evr_simulations(
        _build_tiny_slot_schema_input_df_without_holo_rare()
    )
    assert "sim_results" in simulation_results


def test_chilling_reign_slot_schema_runtime_fails_loudly_without_probability_tables(monkeypatch):
    card_pool = {
        "common": [{"value": 0.1}],
        "uncommon": [{"value": 0.2}],
        "reverse": [{"value": 0.3}],
        "rare": [{"value": 1.0}],
        "hit": [{"value": 5.0}],
    }

    with pytest.raises(ValueError, match="probability_attr='RARE_SLOT_PROBABILITY'"):
        simulate_slot_schema_packs_real(SetChillingReignConfig, card_pool, num_packs=1, rng=random.Random(7))
