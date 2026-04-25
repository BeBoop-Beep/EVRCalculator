from collections import defaultdict

import numpy as np
import pandas as pd

from backend.calculations.utils.reverse_pool import REVERSE_PRICE_COLUMN, build_reverse_eligible_pool
from backend.constants.tcg.pokemon.scarletAndVioletEra.obsidianFlames import SetObsidianFlamesConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import SetPrismaticEvolutionsConfig
from backend.simulations.monteCarloSimV2 import sample_cards_for_slot_outcomes, validate_pack_state_model
from backend.simulations.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups
from backend.simulations.utils.packStateModels.packStateCoercion import (
    count_non_regular_hits,
    coerce_slot_outcomes,
)
from backend.simulations.utils.reverse_state_compatibility_audit import (
    audit_non_pattern_sets_compatibility,
    audit_pattern_state_resolution,
    audit_reverse_pool_composition,
)
from backend.simulations.utils.simulationTokenResolver import resolve_hit_pool_rows


class _PatternReverseEligibleConfig(SetPrismaticEvolutionsConfig):
    @classmethod
    def get_reverse_eligible_rarities(cls):
        base = super().get_reverse_eligible_rarities()
        return [*base, "poke ball pattern", "master ball pattern"]


class _PatternStateConfig(SetPrismaticEvolutionsConfig):
    PACK_STATE_MODEL = {
        "state_probabilities": {
            "pattern_state": 1.0,
        },
        "state_outcomes": {
            "pattern_state": {
                "rare": "master ball pattern",
                "reverse_1": "regular reverse",
                "reverse_2": "regular reverse",
            }
        },
    }


class _PatternConstraintConfig(SetPrismaticEvolutionsConfig):
    PACK_STATE_MODEL = {
        "state_probabilities": {
            "pattern_plus_double": 1.0,
        },
        "state_outcomes": {
            "pattern_plus_double": {
                "rare": "double rare",
                "reverse_1": "poke ball pattern",
                "reverse_2": "regular reverse",
            }
        },
    }


def _build_pattern_mix_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Card Name": [
                "Common A",
                "Uncommon A",
                "Rare A",
                "Rare B",
                "Poke Pattern Rare",
                "Master Pattern Rare",
                "Double Rare A",
            ],
            "Rarity": [
                "common",
                "uncommon",
                "rare",
                "rare",
                "rare",
                "rare",
                "double rare",
            ],
            "Special Type": ["", "", "", "", "poke ball", "master ball", ""],
            "Price ($)": [0.11, 0.22, 1.0, 1.1, 2.1, 5.0, 4.5],
            REVERSE_PRICE_COLUMN: [0.18, 0.27, 0.5, 0.55, 2.5, 6.25, np.nan],
        }
    )


def _build_pattern_state_pools() -> dict:
    common = pd.DataFrame(
        {
            "Card Name": ["Common A", "Common B", "Common C", "Common D"],
            "Rarity": ["common", "common", "common", "common"],
            "Price ($)": [0.1, 0.1, 0.1, 0.1],
        }
    )
    uncommon = pd.DataFrame(
        {
            "Card Name": ["Uncommon A", "Uncommon B", "Uncommon C"],
            "Rarity": ["uncommon", "uncommon", "uncommon"],
            "Price ($)": [0.2, 0.2, 0.2],
        }
    )
    rare = pd.DataFrame(
        {
            "Card Name": ["Rare A", "Rare B"],
            "Rarity": ["rare", "rare"],
            "Price ($)": [1.0, 1.2],
        }
    )
    reverse = pd.DataFrame(
        {
            "Card Name": ["Reverse A", "Reverse B"],
            REVERSE_PRICE_COLUMN: [0.4, 0.5],
        }
    )
    hit = pd.DataFrame(
        {
            "Card Name": [
                "Poke Pattern 1",
                "Master Pattern 1",
                "Double Rare A",
                "Hyper Rare A",
                "SIR A",
            ],
            "Rarity": ["rare", "rare", "double rare", "hyper rare", "special illustration rare"],
            "Special Type": ["poke ball", "master ball", "", "", ""],
            "Price ($)": [2.5, 5.0, 4.0, 20.0, 30.0],
        }
    )
    return {
        "common": common,
        "uncommon": uncommon,
        "rare": rare,
        "reverse": reverse,
        "hit": hit,
    }


def _build_non_pattern_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Card Name": [
                "Common A",
                "Common B",
                "Common C",
                "Common D",
                "Uncommon A",
                "Uncommon B",
                "Uncommon C",
                "Rare A",
                "Rare B",
                "Illustration Rare A",
                "Special Illustration Rare A",
                "Hyper Rare A",
                "Double Rare A",
                "Ultra Rare A",
            ],
            "Rarity": [
                "common",
                "common",
                "common",
                "common",
                "uncommon",
                "uncommon",
                "uncommon",
                "rare",
                "rare",
                "illustration rare",
                "special illustration rare",
                "hyper rare",
                "double rare",
                "ultra rare",
            ],
            "Special Type": [""] * 14,
            "Price ($)": [
                0.1,
                0.1,
                0.1,
                0.1,
                0.2,
                0.2,
                0.2,
                1.0,
                1.2,
                5.5,
                25.0,
                18.0,
                4.0,
                9.0,
            ],
            REVERSE_PRICE_COLUMN: [
                0.15,
                0.16,
                0.17,
                0.18,
                0.25,
                0.27,
                0.29,
                0.45,
                0.48,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
            ],
        }
    )


def test_reverse_pool_includes_pattern_rows():
    df = _build_pattern_mix_df()
    groups = extract_scarletandviolet_card_groups(_PatternReverseEligibleConfig, df)
    reverse_pool = groups["reverse"]

    assert "Poke Pattern Rare" in set(reverse_pool["Card Name"])
    assert "Master Pattern Rare" in set(reverse_pool["Card Name"])
    assert "Rare A" in set(reverse_pool["Card Name"])
    assert "Uncommon A" in set(reverse_pool["Card Name"])
    assert reverse_pool[REVERSE_PRICE_COLUMN].notna().all()



def test_reverse_pool_excludes_rows_without_reverse_price():
    df = _build_pattern_mix_df().copy()
    df.loc[df["Card Name"].eq("Master Pattern Rare"), REVERSE_PRICE_COLUMN] = np.nan
    df.loc[df["Card Name"].eq("Rare A"), REVERSE_PRICE_COLUMN] = np.nan

    reverse_pool = build_reverse_eligible_pool(_PatternReverseEligibleConfig, df)
    reverse_names = set(reverse_pool["Card Name"])

    assert "Master Pattern Rare" not in reverse_names
    assert "Rare A" not in reverse_names



def test_pattern_state_outcomes_resolvable():
    pools = _build_pattern_state_pools()
    audit = audit_pattern_state_resolution(_PatternStateConfig, pools)

    assert audit["is_valid"], audit["issues"]
    assert audit["pattern_outcomes_resolvable"]
    outcome = audit["pattern_outcomes_resolvable"][0]
    assert outcome["token"] == "master ball pattern"
    assert outcome["resolved_rows"] > 0



def test_regular_reverse_still_works():
    pools = _build_pattern_state_pools()
    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)

    sampled = sample_cards_for_slot_outcomes(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=pools["hit"],
        reverse_pool=pools["reverse"],
        slot_outcomes={"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"},
        slots_per_rarity={"common": 4, "uncommon": 3, "reverse": 2, "rare": 1},
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        rng=np.random.default_rng(7),
    )

    assert sampled["slot_cards"]["reverse_1"] in {"Reverse A", "Reverse B"}
    assert sampled["slot_cards"]["reverse_2"] in {"Reverse A", "Reverse B"}
    assert rarity_counts["regular reverse"] == 2



def test_state_constraints_with_pattern_outcomes():
    model = validate_pack_state_model(_PatternConstraintConfig, _build_pattern_state_pools())
    constraints = model["constraints"]
    raw_state = model["state_outcomes"]["pattern_plus_double"]

    coerced = coerce_slot_outcomes(raw_state, constraints)
    assert coerced["reverse_1"] == "poke ball pattern"
    assert coerced["rare"] == "double rare"
    assert count_non_regular_hits(coerced) <= constraints["max_non_regular_hits"]



def test_prismatic_reverse_special_outcomes():
    pools = _build_pattern_state_pools()

    poke_rows, _ = resolve_hit_pool_rows(pools["hit"], "poke ball pattern", mode="pattern")
    master_rows, _ = resolve_hit_pool_rows(pools["hit"], "master ball pattern", mode="pattern")
    assert not poke_rows.empty
    assert not master_rows.empty

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    sampled = sample_cards_for_slot_outcomes(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=pools["hit"],
        reverse_pool=pools["reverse"],
        slot_outcomes={
            "rare": "poke ball pattern",
            "reverse_1": "master ball pattern",
            "reverse_2": "regular reverse",
        },
        slots_per_rarity={"common": 4, "uncommon": 3, "reverse": 2, "rare": 1},
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        rng=np.random.default_rng(1),
    )

    assert sampled["slot_cards"]["rare"] == "Poke Pattern 1"
    assert sampled["slot_cards"]["reverse_1"] == "Master Pattern 1"
    assert sampled["slot_values"]["rare"] == 2.5
    assert sampled["slot_values"]["reverse_1"] == 5.0



def test_non_prismatic_sets_unchanged():
    df = _build_non_pattern_df()
    audit = audit_non_pattern_sets_compatibility(SetObsidianFlamesConfig, df)

    assert audit["is_valid"], audit["issues"]
    assert audit["tested_sets"][0]["source_pattern_rows"] == 0
    assert audit["tested_sets"][0]["reverse_pattern_rows"] == 0
    assert audit["tested_sets"][0]["hit_pattern_tokens"] == []



def test_reverse_price_column_present_for_patterns():
    df = _build_pattern_mix_df()
    audit = audit_reverse_pool_composition(_PatternReverseEligibleConfig, df)

    assert audit["is_valid"], audit["issues"]
    reverse_pool = build_reverse_eligible_pool(_PatternReverseEligibleConfig, df)
    pattern_rows = reverse_pool[reverse_pool["Card Name"].isin(["Poke Pattern Rare", "Master Pattern Rare"])]

    assert not pattern_rows.empty
    assert pattern_rows[REVERSE_PRICE_COLUMN].notna().all()
    assert (pattern_rows[REVERSE_PRICE_COLUMN] > 0).all()
    assert (pattern_rows[REVERSE_PRICE_COLUMN] < 100).all()
