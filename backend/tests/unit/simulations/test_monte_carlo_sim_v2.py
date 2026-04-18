from collections import Counter, defaultdict

import numpy as np
import pandas as pd
import pytest

from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import (
    SetPrismaticEvolutionsConfig,
)
from backend.constants.tcg.pokemon.scarletAndVioletEra.blackBolt import SetBlackBoltConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.scarletAndViolet151 import Set151Config
from backend.constants.tcg.pokemon.scarletAndVioletEra.whiteFlare import SetWhiteFlareConfig
from backend.simulations.monteCarloSim import print_simulation_summary
from backend.simulations.monteCarloSim import run_simulation
from backend.simulations.monteCarloSimV2 import (
    make_simulate_pack_fn_v2,
    print_simulation_summary_v2,
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
    god_pack_cards = SetPrismaticEvolutionsConfig.GOD_PACK_CONFIG["strategy"]["cards"]
    god_cards = pd.DataFrame(
        {
            "Card Name": [card["name"] for card in god_pack_cards],
            "Card Number": [card.get("number", "") for card in god_pack_cards],
            "Price ($)": [10.0] * len(god_pack_cards),
            "Rarity": [card["rarity"] for card in god_pack_cards],
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
    # Commons and uncommons must now appear in rarity tracking.
    assert rarity_counts["common"] == 4
    assert rarity_counts["uncommon"] == 3
    assert rarity_values["common"] > 0
    assert rarity_values["uncommon"] > 0


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


def test_special_pack_fixed_card_objects_preserve_resolved_rarities_and_values():
    class StructuredGodConfig(DummySVConfig):
        GOD_PACK_CONFIG = {
            "enabled": True,
            "pull_rate": 1.0,
            "strategy": {
                "type": "fixed",
                "cards": [
                    {"name": "Charmander", "number": "168/165", "rarity": "illustration rare"},
                    {"name": "Charmeleon", "number": "169/165", "rarity": "illustration rare"},
                    {"name": "Charizard ex", "number": "199/165", "rarity": "special illustration rare"},
                ],
            },
        }

    common = pd.DataFrame(
        {
            "Card Name": [f"Common {i}" for i in range(1, 6)],
            "Price ($)": [0.10] * 5,
            "Rarity": ["common"] * 5,
            "Card Number": ["001/165", "002/165", "003/165", "004/165", "005/165"],
        }
    )
    uncommon = pd.DataFrame(
        {
            "Card Name": [f"Uncommon {i}" for i in range(1, 5)],
            "Price ($)": [0.20] * 4,
            "Rarity": ["uncommon"] * 4,
            "Card Number": ["051/165", "052/165", "053/165", "054/165"],
        }
    )
    rare = pd.DataFrame(
        {
            "Card Name": ["Rare A"],
            "Price ($)": [0.75],
            "Rarity": ["rare"],
            "Card Number": ["100/165"],
        }
    )
    reverse = pd.DataFrame(
        {
            "Card Name": ["Reverse A"],
            "EV_Reverse": [0.35],
        }
    )
    hit = pd.DataFrame(
        {
            "Card Name": [
                "Charmander",
                "Charmeleon",
                "Charizard ex",
                "Charizard ex",
            ],
            "Card Number": ["168/165", "169/165", "199/165", "006/165"],
            "Price ($)": [8.0, 6.0, 45.0, 5.0],
            "Rarity": [
                "illustration rare",
                "illustration rare",
                "special illustration rare",
                "double rare",
            ],
        }
    )
    df = pd.concat([common, uncommon, rare, hit], ignore_index=True)

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    logs = []

    fn = make_simulate_pack_fn_v2(
        common_cards=common,
        uncommon_cards=uncommon,
        rare_cards=rare,
        hit_cards=hit,
        reverse_pool=reverse,
        slots_per_rarity=StructuredGodConfig.SLOTS_PER_RARITY,
        config=StructuredGodConfig,
        df=df,
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        pack_logs=logs,
        rng=np.random.default_rng(5),
    )

    value, pack_data = fn(return_pack_data=True)

    assert value == pytest.approx(59.0)
    assert pack_data["entry_path"] == "god"
    assert pack_data["special_pack_rarities"] == [
        "illustration rare",
        "illustration rare",
        "special illustration rare",
    ]
    assert rarity_counts["illustration rare"] == 2
    assert rarity_counts["special illustration rare"] == 1
    assert rarity_counts["double rare"] == 0
    assert rarity_values["illustration rare"] == pytest.approx(14.0)
    assert rarity_values["special illustration rare"] == pytest.approx(45.0)


def test_actual_prismatic_fixed_config_supports_name_only_master_ball_entry_in_v2(prismatic_pools):
    class ForcedPrismaticConfig(DummySVConfig):
        GOD_PACK_CONFIG = {
            "enabled": True,
            "pull_rate": 1.0,
            "strategy": SetPrismaticEvolutionsConfig.GOD_PACK_CONFIG["strategy"],
        }

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    logs = []
    fn = make_simulate_pack_fn_v2(
        common_cards=prismatic_pools["common"],
        uncommon_cards=prismatic_pools["uncommon"],
        rare_cards=prismatic_pools["rare"],
        hit_cards=prismatic_pools["hit"],
        reverse_pool=prismatic_pools["reverse"],
        slots_per_rarity=ForcedPrismaticConfig.SLOTS_PER_RARITY,
        config=ForcedPrismaticConfig,
        df=prismatic_pools["df"],
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        pack_logs=logs,
        rng=np.random.default_rng(21),
    )

    value, pack_data = fn(return_pack_data=True)

    assert value == pytest.approx(100.0)
    assert pack_data["entry_path"] == "god"
    assert pack_data["state"] == "god_pack"
    assert pack_data["special_pack_rarities"].count("master ball pattern") == 1
    assert pack_data["special_pack_rarities"].count("special illustration rare") == 9
    assert rarity_counts["master ball pattern"] == 1
    assert rarity_counts["special illustration rare"] == 9
    assert sum(rarity_counts.values()) == 10


def test_actual_151_fixed_packs_increment_god_pack_state_counts_in_v2():
    class Forced151Config(DummySVConfig):
        GOD_PACK_CONFIG = {
            "enabled": True,
            "pull_rate": 1.0,
            "strategy": Set151Config.GOD_PACK_CONFIG["strategy"],
        }

    common = pd.DataFrame(
        {
            "Card Name": [f"Common {i}" for i in range(1, 6)],
            "Price ($)": [0.10] * 5,
            "Rarity": ["common"] * 5,
            "Card Number": [f"00{i}/165" for i in range(1, 6)],
        }
    )
    uncommon = pd.DataFrame(
        {
            "Card Name": [f"Uncommon {i}" for i in range(1, 5)],
            "Price ($)": [0.20] * 4,
            "Rarity": ["uncommon"] * 4,
            "Card Number": [f"05{i}/165" for i in range(1, 5)],
        }
    )
    hit_rows = []
    for pack in Set151Config.GOD_PACK_CONFIG["strategy"]["packs"]:
        for card in pack["cards"]:
            hit_rows.append(
                {
                    "Card Name": card["name"],
                    "Card Number": card["number"],
                    "Price ($)": 8.0 if card["rarity"] == "illustration rare" else 45.0,
                    "Rarity": card["rarity"],
                }
            )
    hit = pd.DataFrame(hit_rows)
    rare = pd.DataFrame(
        {
            "Card Name": ["Rare A"],
            "Price ($)": [0.75],
            "Rarity": ["rare"],
            "Card Number": ["100/165"],
        }
    )
    reverse = pd.DataFrame(
        {
            "Card Name": ["Reverse A"],
            "EV_Reverse": [0.35],
        }
    )
    df = pd.concat([common, uncommon, rare, hit], ignore_index=True)

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    logs = []
    fn = make_simulate_pack_fn_v2(
        common_cards=common,
        uncommon_cards=uncommon,
        rare_cards=rare,
        hit_cards=hit,
        reverse_pool=reverse,
        slots_per_rarity=Forced151Config.SLOTS_PER_RARITY,
        config=Forced151Config,
        df=df,
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        pack_logs=logs,
        rng=np.random.default_rng(33),
    )

    sim = run_simulation_v2(lambda: fn(return_pack_data=True), rarity_counts, rarity_values, n=4)

    assert sim["pack_path_counts"]["god"] == 4
    assert all(record["entry_path"] == "god" for record in logs)
    assert all(record["state"] == "god_pack" for record in logs)
    assert rarity_counts["common"] == 16
    assert rarity_counts["uncommon"] == 12
    assert rarity_counts["illustration rare"] == 8
    assert rarity_counts["special illustration rare"] == 4
    assert sim["mean"] == pytest.approx(62.0)


@pytest.mark.parametrize("config_cls", [SetWhiteFlareConfig, SetBlackBoltConfig])
def test_white_flare_and_black_bolt_still_use_random_rarity_rule_special_packs_in_v2(config_cls, pools):
    forced_config = type(
        f"Forced{config_cls.__name__}",
        (DummySVConfig,),
        {
            "GOD_PACK_CONFIG": {
                "enabled": True,
                "pull_rate": 1.0,
                "strategy": config_cls.GOD_PACK_CONFIG["strategy"],
            }
        },
    )

    hit = pd.DataFrame(
        {
            "Card Name": [f"IR {i}" for i in range(1, 4)] + ["SIR 1", "SIR 2"],
            "Price ($)": [7.5, 7.8, 8.1, 31.0, 32.0],
            "Rarity": [
                "illustration rare",
                "illustration rare",
                "illustration rare",
                "special illustration rare",
                "special illustration rare",
            ],
        }
    )
    df = pd.concat([pools["common"], pools["uncommon"], pools["rare"], hit], ignore_index=True)

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    logs = []
    fn = make_simulate_pack_fn_v2(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=hit,
        reverse_pool=pools["reverse"],
        slots_per_rarity=forced_config.SLOTS_PER_RARITY,
        config=forced_config,
        df=df,
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        pack_logs=logs,
        rng=np.random.default_rng(44),
    )

    value, pack_data = fn(return_pack_data=True)

    assert value > 0
    assert pack_data["entry_path"] == "god"
    assert pack_data["state"] == "god_pack"
    assert Counter(pack_data["special_pack_rarities"]) == {
        "illustration rare": 9,
        "special illustration rare": 1,
    }
    assert rarity_counts["illustration rare"] == 9
    assert rarity_counts["special illustration rare"] == 1
    assert rarity_counts["common"] == 0
    assert rarity_counts["uncommon"] == 0


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

    # Commons and uncommons from normal packs must now appear in the rarity summary.
    assert rarity_counts["common"] == len(normal_logs) * DummySVConfig.SLOTS_PER_RARITY["common"]
    assert rarity_counts["uncommon"] == len(normal_logs) * DummySVConfig.SLOTS_PER_RARITY["uncommon"]
    assert rarity_values["common"] > 0
    assert rarity_values["uncommon"] > 0


def test_sample_cards_for_slot_outcomes_tracks_common_uncommon_rarity_counts():
    """Commons and uncommons from a normal pack are counted and valued exactly once.

    Uses uniform-price pools so expected totals are deterministic regardless of
    which specific rows the RNG selects (sampling with replacement, all prices equal).
    """
    # All commons priced identically -> regardless of which 4 are drawn the total is always 4 * 0.10.
    fixed_common = pd.DataFrame({
        "Card Name": ["C1", "C2", "C3", "C4", "C5"],
        "Price ($)": [0.10, 0.10, 0.10, 0.10, 0.10],
        "Rarity": ["common"] * 5,
    })
    # All uncommons priced identically -> regardless of which 3 are drawn total is always 3 * 0.25.
    fixed_uncommon = pd.DataFrame({
        "Card Name": ["U1", "U2", "U3", "U4"],
        "Price ($)": [0.25, 0.25, 0.25, 0.25],
        "Rarity": ["uncommon"] * 4,
    })
    rare_pool = pd.DataFrame({
        "Card Name": ["Rare X"],
        "Price ($)": [1.00],
        "Rarity": ["rare"],
    })
    reverse_pool = pd.DataFrame({
        "Card Name": ["Rev X"],
        "EV_Reverse": [0.35],
    })

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    rng = np.random.default_rng(99)

    result = sample_cards_for_slot_outcomes(
        common_cards=fixed_common,
        uncommon_cards=fixed_uncommon,
        rare_cards=rare_pool,
        hit_cards=pd.DataFrame(columns=["Card Name", "Price ($)", "Rarity"]),
        reverse_pool=reverse_pool,
        slot_outcomes={"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"},
        slots_per_rarity={"common": 4, "uncommon": 3, "reverse": 2, "rare": 1},
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        rng=rng,
    )

    # Counts are exact regardless of which rows were sampled.
    assert rarity_counts["common"] == 4
    assert rarity_counts["uncommon"] == 3

    # Value totals are exact because all cards in each pool have the same price.
    assert pytest.approx(rarity_values["common"], abs=1e-9) == 4 * 0.10
    assert pytest.approx(rarity_values["uncommon"], abs=1e-9) == 3 * 0.25

    # common/uncommon values are included in the pack total_value — not double-counted.
    expected_common_uncommon = 4 * 0.10 + 3 * 0.25
    assert result["total_value"] >= expected_common_uncommon  # also includes rare/reverse slots


def test_sample_cards_for_slot_outcomes_no_double_counting_across_two_packs():
    """Calling sample_cards_for_slot_outcomes twice accumulates counts correctly (no resets)."""
    fixed_common = pd.DataFrame({
        "Card Name": ["C1", "C2"],
        "Price ($)": [0.10, 0.10],
        "Rarity": ["common"] * 2,
    })
    fixed_uncommon = pd.DataFrame({
        "Card Name": ["U1", "U2"],
        "Price ($)": [0.20, 0.20],
        "Rarity": ["uncommon"] * 2,
    })
    rare_pool = pd.DataFrame({"Card Name": ["R1"], "Price ($)": [1.0], "Rarity": ["rare"]})
    reverse_pool = pd.DataFrame({"Card Name": ["Rev1"], "EV_Reverse": [0.30]})

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    slots = {"common": 2, "uncommon": 2, "reverse": 2, "rare": 1}
    outcomes = {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"}
    kwargs = dict(
        common_cards=fixed_common,
        uncommon_cards=fixed_uncommon,
        rare_cards=rare_pool,
        hit_cards=pd.DataFrame(columns=["Card Name", "Price ($)", "Rarity"]),
        reverse_pool=reverse_pool,
        slot_outcomes=outcomes,
        slots_per_rarity=slots,
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
    )

    sample_cards_for_slot_outcomes(**kwargs, rng=np.random.default_rng(1))
    sample_cards_for_slot_outcomes(**kwargs, rng=np.random.default_rng(2))

    assert rarity_counts["common"] == 4   # 2 cards × 2 packs
    assert rarity_counts["uncommon"] == 4  # 2 cards × 2 packs
    assert pytest.approx(rarity_values["common"], abs=1e-9) == 4 * 0.10
    assert pytest.approx(rarity_values["uncommon"], abs=1e-9) == 4 * 0.20


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


def test_pull_summary_v2_prints_high_precision_avg_and_clear_total_label(capsys):
    sim_results = {
        "mean": 0.0,
        "std_dev": 0.0,
        "min": 0.0,
        "max": 0.0,
        "percentiles": {
            "5th": 0.0,
            "25th": 0.0,
            "50th (median)": 0.0,
            "75th": 0.0,
            "90th": 0.0,
            "95th": 0.0,
            "99th": 0.0,
        },
        "rarity_pull_counts": {"ultra rare": 3},
        "rarity_value_totals": {"ultra rare": 1.0},
        "pack_path_counts": {},
        "pack_state_counts": {},
    }

    print_simulation_summary_v2(sim_results, n_simulations=3)
    output = capsys.readouterr().out

    assert "avg value: $0.333333" in output
    assert "total sampled value: $1.00" in output


def test_pull_summary_v1_and_v2_displayed_avg_matches_total_sampled_value(capsys):
    sim_results = {
        "values": [0.0, 0.0, 0.0],
        "mean": 0.0,
        "std_dev": 0.0,
        "min": 0.0,
        "max": 0.0,
        "percentiles": {
            "5th": 0.0,
            "25th": 0.0,
            "50th (median)": 0.0,
            "75th": 0.0,
            "90th": 0.0,
            "95th": 0.0,
            "99th": 0.0,
        },
        "rarity_pull_counts": {"double rare": 3},
        "rarity_value_totals": {"double rare": 1.0},
    }

    print_simulation_summary(sim_results, n_simulations=3)
    out_v1 = capsys.readouterr().out
    assert "avg value: $0.333333" in out_v1
    assert "total sampled value: $1.00" in out_v1

    print_simulation_summary_v2(
        {
            **sim_results,
            "pack_path_counts": {},
            "pack_state_counts": {},
        },
        n_simulations=3,
    )
    out_v2 = capsys.readouterr().out
    assert "avg value: $0.333333" in out_v2
    assert "total sampled value: $1.00" in out_v2
