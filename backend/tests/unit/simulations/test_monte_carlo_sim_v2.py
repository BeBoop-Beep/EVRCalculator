from collections import defaultdict

import numpy as np
import pandas as pd
import pytest

from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import (
    SetPrismaticEvolutionsConfig,
)
from backend.simulations.monteCarloSim import run_simulation
from backend.simulations.monteCarloSimV2 import (
    make_simulate_pack_fn_v2,
    resolve_slot_outcomes_from_state,
    run_simulation_v2,
    sample_cards_for_slot_outcomes,
    validate_pack_state_model,
)


class DummySVConfig:
    USE_MONTE_CARLO_V2 = True
    ERA = "Scarlet and Violet"
    SLOTS_PER_RARITY = {"common": 4, "uncommon": 3, "reverse": 2, "rare": 1}

    RARE_SLOT_PROBABILITY = {
        "double rare": 0.15,
        "ultra rare": 0.10,
        "rare": 0.75,
    }

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "ace spec rare": 0.10,
            "poke ball pattern": 0.20,
            "regular reverse": 0.70,
        },
        "slot_2": {
            "illustration rare": 0.10,
            "special illustration rare": 0.02,
            "hyper rare": 0.01,
            "master ball pattern": 0.05,
            "regular reverse": 0.82,
        },
    }

    GOD_PACK_CONFIG = {"enabled": False, "pull_rate": 0.0, "strategy": {}}
    DEMI_GOD_PACK_CONFIG = {"enabled": False, "pull_rate": 0.0, "strategy": {}}


@pytest.fixture
def pools():
    common = pd.DataFrame(
        {
            "Card Name": [f"Common {i}" for i in range(1, 6)],
            "Price ($)": [0.10, 0.12, 0.08, 0.11, 0.09],
            "Rarity": ["common"] * 5,
        }
    )
    uncommon = pd.DataFrame(
        {
            "Card Name": [f"Uncommon {i}" for i in range(1, 5)],
            "Price ($)": [0.20, 0.25, 0.18, 0.22],
            "Rarity": ["uncommon"] * 4,
        }
    )
    rare = pd.DataFrame(
        {
            "Card Name": ["Rare A", "Rare B", "Rare C"],
            "Price ($)": [0.75, 0.95, 1.10],
            "Rarity": ["rare", "rare", "rare"],
        }
    )
    reverse = pd.DataFrame(
        {
            "Card Name": ["Reverse A", "Reverse B", "Reverse C", "Reverse D"],
            "EV_Reverse": [0.35, 0.40, 0.28, 0.32],
        }
    )
    hit = pd.DataFrame(
        {
            "Card Name": [
                "Double Rare A",
                "Ultra Rare A",
                "Illustration Rare A",
                "Special Illustration Rare A",
                "Hyper Rare A",
                "Ace Spec A",
                "Poke Pattern A",
                "Master Pattern A",
            ],
            "Price ($)": [
                4.00,
                9.50,
                7.25,
                28.0,
                22.0,
                3.75,
                2.20,
                5.0,
            ],
            "Rarity": [
                "double rare",
                "ultra rare",
                "illustration rare",
                "special illustration rare",
                "hyper rare",
                "ace spec rare",
                "poke ball pattern",
                "master ball pattern",
            ],
        }
    )
    full_df = pd.concat([common, uncommon, rare, hit], ignore_index=True)
    return {
        "common": common,
        "uncommon": uncommon,
        "rare": rare,
        "reverse": reverse,
        "hit": hit,
        "df": full_df,
    }


@pytest.fixture
def prismatic_pools():
    commons = pd.DataFrame(
        {
            "Card Name": ["Common A", "Common B", "Common C", "Common D", "Common E"],
            "Price ($)": [0.09, 0.11, 0.08, 0.10, 0.12],
            "Rarity": ["common"] * 5,
        }
    )
    uncommons = pd.DataFrame(
        {
            "Card Name": ["Uncommon A", "Uncommon B", "Uncommon C", "Uncommon D"],
            "Price ($)": [0.24, 0.19, 0.22, 0.27],
            "Rarity": ["uncommon"] * 4,
        }
    )
    rares = pd.DataFrame(
        {
            "Card Name": ["Rare 1", "Rare 2", "Rare 3"],
            "Price ($)": [0.9, 1.1, 1.0],
            "Rarity": ["rare", "rare", "rare"],
        }
    )
    reverse = pd.DataFrame(
        {
            "Card Name": ["Reverse 1", "Reverse 2", "Reverse 3", "Reverse 4"],
            "EV_Reverse": [0.35, 0.28, 0.31, 0.45],
        }
    )
    hit = pd.DataFrame(
        {
            "Card Name": [
                "Double Rare X",
                "Ultra Rare X",
                "Illustration Rare X",
                "Special Illustration Rare X",
                "Hyper Rare X",
                "Ace Spec X",
                "Poke Ball Pattern X",
                "Master Ball Pattern X",
            ],
            "Price ($)": [4.0, 9.0, 7.5, 31.0, 26.0, 3.0, 1.9, 4.6],
            "Rarity": [
                "double rare",
                "ultra rare",
                "illustration rare",
                "special illustration rare",
                "hyper rare",
                "ace spec rare",
                "poke ball pattern",
                "master ball pattern",
            ],
        }
    )

    # Include configured god-pack card names so fixed-card lookup never fails.
    god_cards = pd.DataFrame(
        {
            "Card Name": SetPrismaticEvolutionsConfig.GOD_PACK_CONFIG["strategy"]["cards"],
            "Price ($)": [10.0] * len(SetPrismaticEvolutionsConfig.GOD_PACK_CONFIG["strategy"]["cards"]),
            "Rarity": ["special illustration rare"] * len(
                SetPrismaticEvolutionsConfig.GOD_PACK_CONFIG["strategy"]["cards"]
            ),
        }
    )

    df = pd.concat([commons, uncommons, rares, hit, god_cards], ignore_index=True)
    return {
        "common": commons,
        "uncommon": uncommons,
        "rare": rares,
        "reverse": reverse,
        "hit": hit,
        "df": df,
    }


def test_validate_pack_state_model_builds_default_sv_model(pools):
    model = validate_pack_state_model(DummySVConfig, pools)
    assert "state_probabilities" in model
    assert "state_outcomes" in model
    assert pytest.approx(1.0, abs=1e-8) == sum(model["state_probabilities"].values())
    assert "baseline" in model["state_probabilities"]
    assert "sir_only" in model["state_probabilities"]
    assert "hyper_only" in model["state_probabilities"]


def test_validate_pack_state_model_rejects_invalid_probability_sum(pools):
    class BadModelConfig(DummySVConfig):
        PACK_STATE_MODEL = {
            "state_probabilities": {"baseline": 0.6, "double_rare_only": 0.5},
            "state_outcomes": {
                "baseline": {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"},
                "double_rare_only": {
                    "rare": "double rare",
                    "reverse_1": "regular reverse",
                    "reverse_2": "regular reverse",
                },
            },
        }

    with pytest.raises(ValueError, match="sum to 1.0"):
        validate_pack_state_model(BadModelConfig, pools)


def test_resolve_slot_outcomes_honors_sir_exclusivity():
    class SirConfig(DummySVConfig):
        PACK_STATE_MODEL = {
            "state_probabilities": {"sir_only": 1.0},
            "state_outcomes": {
                "sir_only": {
                    "rare": "ultra rare",
                    "reverse_1": "ace spec rare",
                    "reverse_2": "special illustration rare",
                }
            },
        }

    resolved = resolve_slot_outcomes_from_state({"state": "sir_only"}, SirConfig)
    assert resolved["reverse_2"] == "special illustration rare"
    assert resolved["rare"] == "rare"
    assert resolved["reverse_1"] == "regular reverse"


def test_resolve_slot_outcomes_honors_hyper_exclusivity():
    class HyperConfig(DummySVConfig):
        PACK_STATE_MODEL = {
            "state_probabilities": {"hyper_only": 1.0},
            "state_outcomes": {
                "hyper_only": {
                    "rare": "double rare",
                    "reverse_1": "ace spec rare",
                    "reverse_2": "hyper rare",
                }
            },
        }

    resolved = resolve_slot_outcomes_from_state({"state": "hyper_only"}, HyperConfig)
    assert resolved == {
        "rare": "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "hyper rare",
    }


def test_bonus_hit_can_coexist_with_primary_hit_but_not_three_hits():
    class BonusConfig(DummySVConfig):
        PACK_STATE_MODEL = {
            "state_probabilities": {"triple_hit": 1.0},
            "state_outcomes": {
                "triple_hit": {
                    "rare": "double rare",
                    "reverse_1": "ace spec rare",
                    "reverse_2": "illustration rare",
                }
            },
        }

    resolved = resolve_slot_outcomes_from_state({"state": "triple_hit"}, BonusConfig)
    non_regular = [r for r in resolved.values() if r not in {"rare", "regular reverse"}]
    assert len(non_regular) == 2
    assert "illustration rare" in non_regular
    assert "double rare" in non_regular


def test_sample_cards_for_slot_outcomes_samples_from_eligible_pools(pools):
    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    rng = np.random.default_rng(7)

    result = sample_cards_for_slot_outcomes(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=pools["hit"],
        reverse_pool=pools["reverse"],
        slot_outcomes={"rare": "double rare", "reverse_1": "regular reverse", "reverse_2": "illustration rare"},
        slots_per_rarity=DummySVConfig.SLOTS_PER_RARITY,
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        rng=rng,
    )

    assert result["common_count"] == 4
    assert result["uncommon_count"] == 3
    assert result["slot_cards"]["rare"] == "Double Rare A"
    assert result["slot_cards"]["reverse_2"] == "Illustration Rare A"
    assert result["slot_cards"]["reverse_1"] in set(pools["reverse"]["Card Name"])
    assert rarity_counts["double rare"] == 1
    assert rarity_counts["regular reverse"] == 1
    assert rarity_counts["illustration rare"] == 1


def test_run_simulation_v2_uses_single_simulated_pack_set():
    counter = {"calls": 0}

    def open_pack_fn():
        counter["calls"] += 1
        return float(counter["calls"])

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    sim = run_simulation_v2(open_pack_fn, rarity_counts, rarity_values, n=25)

    assert len(sim["values"]) == 25
    assert counter["calls"] == 25
    assert pytest.approx(np.mean(sim["values"])) == sim["mean"]


def test_run_simulation_v2_debug_export_returns_dataframe():
    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)

    def open_pack_fn():
        return 2.5, {
            "entry_path": "normal",
            "state": "baseline",
            "slot_outcomes": {
                "rare": "rare",
                "reverse_1": "regular reverse",
                "reverse_2": "regular reverse",
            },
            "slot_values": {"rare": 1.0, "reverse_1": 0.5, "reverse_2": 1.0},
        }

    sim = run_simulation_v2(open_pack_fn, rarity_counts, rarity_values, n=4, export_debug_df=True)
    assert "debug_df" in sim
    assert len(sim["debug_df"]) == 4
    assert set(["pack_state", "entry_path", "slot_outcomes", "slot_values", "total_value"]).issubset(
        sim["debug_df"].columns
    )


def test_special_pack_bypass_path_skips_normal_state(pools):
    class SpecialConfig(DummySVConfig):
        GOD_PACK_CONFIG = {
            "enabled": True,
            "pull_rate": 1.0,
            "strategy": {"type": "fixed", "cards": ["Special Illustration Rare A"]},
        }

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    logs = []
    fn = make_simulate_pack_fn_v2(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=pools["hit"],
        reverse_pool=pools["reverse"],
        slots_per_rarity=SpecialConfig.SLOTS_PER_RARITY,
        config=SpecialConfig,
        df=pools["df"],
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        pack_logs=logs,
        rng=np.random.default_rng(12),
    )

    value, pack_data = fn(return_pack_data=True)
    assert value > 0
    assert pack_data["entry_path"] == "god"
    assert pack_data["state"] == "god_pack"
    assert len(rarity_counts) > 0
    assert sum(rarity_counts.values()) == len(pack_data["special_pack_rarities"])


def test_demi_god_pack_updates_rarity_tracking(pools):
    class DemiConfig(DummySVConfig):
        GOD_PACK_CONFIG = {"enabled": False, "pull_rate": 0.0, "strategy": {}}
        DEMI_GOD_PACK_CONFIG = {
            "enabled": True,
            "pull_rate": 1.0,
            "strategy": {
                "type": "random",
                "rules": {
                    "rarities": {
                        "common": 4,
                        "uncommon": 3,
                        "special illustration rare": 2,
                        "hyper rare": 1,
                    }
                },
            },
        }

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    logs = []
    fn = make_simulate_pack_fn_v2(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=pools["hit"],
        reverse_pool=pools["reverse"],
        slots_per_rarity=DemiConfig.SLOTS_PER_RARITY,
        config=DemiConfig,
        df=pools["df"],
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        pack_logs=logs,
        rng=np.random.default_rng(1234),
    )

    _, pack_data = fn(return_pack_data=True)
    assert pack_data["entry_path"] == "demi_god"
    assert rarity_counts["common"] == 4
    assert rarity_counts["uncommon"] == 3
    assert rarity_counts["special illustration rare"] == 2
    assert rarity_counts["hyper rare"] == 1


def test_normal_pack_invariants_and_tracker_alignment(pools):
    rng = np.random.default_rng(17)
    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    logs = []

    fn = make_simulate_pack_fn_v2(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=pools["hit"],
        reverse_pool=pools["reverse"],
        slots_per_rarity=DummySVConfig.SLOTS_PER_RARITY,
        config=DummySVConfig,
        df=pools["df"],
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        pack_logs=logs,
        rng=rng,
    )

    sim = run_simulation_v2(lambda: fn(return_pack_data=True), rarity_counts, rarity_values, n=3000)

    normal_logs = [x for x in logs if x["entry_path"] == "normal"]
    major_hits = {
        "double rare",
        "ultra rare",
        "hyper rare",
        "illustration rare",
        "special illustration rare",
        "ace spec rare",
        "poke ball pattern",
        "master ball pattern",
    }

    per_rarity_count = defaultdict(int)
    per_rarity_values = defaultdict(float)

    for record in normal_logs:
        outcomes = record["slot_outcomes"]
        values = record["slot_values"]

        if outcomes["reverse_2"] == "special illustration rare":
            assert outcomes["rare"] == "rare"
            assert outcomes["reverse_1"] == "regular reverse"
        if outcomes["reverse_2"] == "hyper rare":
            assert outcomes["rare"] == "rare"
            assert outcomes["reverse_1"] == "regular reverse"
        assert not ({"illustration rare", "special illustration rare"}.issubset(set(outcomes.values())))
        assert not ({"special illustration rare", "hyper rare"}.issubset(set(outcomes.values())))
        assert not ({"illustration rare", "hyper rare"}.issubset(set(outcomes.values())))
        assert outcomes["reverse_2"] in {
            "regular reverse",
            "illustration rare",
            "special illustration rare",
            "hyper rare",
            "master ball pattern",
        }

        major_count = sum(1 for rarity in outcomes.values() if rarity in major_hits)
        assert major_count <= 2

        state_expected = resolve_slot_outcomes_from_state({"state": record["state"]}, DummySVConfig)
        assert outcomes == state_expected

        for slot_name in ("rare", "reverse_1", "reverse_2"):
            rarity = outcomes[slot_name]
            card_name = record["slot_cards"][slot_name]
            if rarity == "rare":
                assert card_name in set(pools["rare"]["Card Name"])
            elif rarity == "regular reverse":
                assert card_name in set(pools["reverse"]["Card Name"])
            else:
                legal_cards = set(
                    pools["hit"][
                        pools["hit"]["Rarity"].str.strip().str.lower() == rarity
                    ]["Card Name"]
                )
                assert card_name in legal_cards

            per_rarity_count[rarity] += 1
            per_rarity_values[rarity] += values[slot_name]

    assert sum(per_rarity_count.values()) == len(normal_logs) * 3
    assert sum(sim["pack_state_counts"].values()) == len(normal_logs)

    for rarity, count in per_rarity_count.items():
        assert rarity_counts[rarity] == count
        assert pytest.approx(per_rarity_values[rarity], abs=1e-9) == rarity_values[rarity]


def test_distribution_sanity_for_special_pack_rates(pools):
    class DistConfig(DummySVConfig):
        GOD_PACK_CONFIG = {"enabled": True, "pull_rate": 0.04, "strategy": {"type": "fixed", "cards": []}}
        DEMI_GOD_PACK_CONFIG = {
            "enabled": True,
            "pull_rate": 0.08,
            "strategy": {"type": "random", "rules": {"count": 0, "rarities": []}},
        }

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    logs = []

    fn = make_simulate_pack_fn_v2(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=pools["hit"],
        reverse_pool=pools["reverse"],
        slots_per_rarity=DistConfig.SLOTS_PER_RARITY,
        config=DistConfig,
        df=pools["df"],
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        pack_logs=logs,
        rng=np.random.default_rng(123),
    )

    sim = run_simulation_v2(lambda: fn(return_pack_data=True), rarity_counts, rarity_values, n=5000)

    god_rate = sim["pack_path_counts"].get("god", 0) / 5000
    demi_rate = sim["pack_path_counts"].get("demi_god", 0) / 5000
    normal_rate = sim["pack_path_counts"].get("normal", 0) / 5000

    assert abs(god_rate - 0.04) < 0.02
    assert abs(demi_rate - 0.08) < 0.025
    assert abs((god_rate + demi_rate + normal_rate) - 1.0) < 1e-9

    normal_logs = [x for x in logs if x["entry_path"] == "normal"]
    assert sum(sim["pack_state_counts"].values()) == len(normal_logs)

    state_model = validate_pack_state_model(DistConfig, pools)
    observed = defaultdict(int)
    for record in normal_logs:
        observed[record["state"]] += 1

    total_normal = max(1, len(normal_logs))
    for state, expected_prob in state_model["state_probabilities"].items():
        observed_prob = observed[state] / total_normal
        assert abs(observed_prob - expected_prob) < 0.08


def test_v1_module_remains_importable_and_usable():
    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    sim = run_simulation(lambda: 1.0, rarity_counts, rarity_values, n=20)
    assert sim["mean"] == 1.0
    assert len(sim["values"]) == 20


def test_prismatic_evolutions_state_integrity(prismatic_pools):
    class PrismaticRegressionConfig(SetPrismaticEvolutionsConfig):
        GOD_PACK_CONFIG = {"enabled": False, "pull_rate": 0.0, "strategy": {}}
        DEMI_GOD_PACK_CONFIG = {"enabled": False, "pull_rate": 0.0, "strategy": {}}

    model = validate_pack_state_model(PrismaticRegressionConfig, prismatic_pools)
    assert pytest.approx(1.0, abs=1e-8) == sum(model["state_probabilities"].values())

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    logs = []

    fn = make_simulate_pack_fn_v2(
        common_cards=prismatic_pools["common"],
        uncommon_cards=prismatic_pools["uncommon"],
        rare_cards=prismatic_pools["rare"],
        hit_cards=prismatic_pools["hit"],
        reverse_pool=prismatic_pools["reverse"],
        slots_per_rarity=PrismaticRegressionConfig.SLOTS_PER_RARITY,
        config=PrismaticRegressionConfig,
        df=prismatic_pools["df"],
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        pack_logs=logs,
        rng=np.random.default_rng(77),
    )

    sim = run_simulation_v2(
        lambda: fn(return_pack_data=True),
        rarity_counts,
        rarity_values,
        n=2500,
        export_debug_df=True,
    )

    assert len(sim["values"]) == 2500
    assert sim["pack_path_counts"].get("normal", 0) == 2500
    assert sum(sim["pack_state_counts"].values()) == 2500
    assert len(sim["debug_df"]) == 2500

    for record in logs:
        outcomes = record["slot_outcomes"]
        outcome_set = set(outcomes.values())
        assert not ({"illustration rare", "special illustration rare"}.issubset(outcome_set))
        assert not ({"special illustration rare", "hyper rare"}.issubset(outcome_set))
        assert not ({"illustration rare", "hyper rare"}.issubset(outcome_set))
