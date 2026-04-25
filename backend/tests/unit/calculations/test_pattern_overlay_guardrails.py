from __future__ import annotations

from types import MappingProxyType

import pandas as pd
import pytest

from backend.calculations.packCalcsRefractored.evrCalculator import PackEVCalculator
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import (
    SetPrismaticEvolutionsConfig,
)
from backend.simulations.utils.extractScarletAndVioletCardGroups import (
    extract_scarletandviolet_card_groups,
)
from backend.simulations.utils.simulationTokenResolver import get_row_match_keys, resolve_hit_pool_rows


class _PatternMathConfig:
    PULL_RATE_MAPPING = MappingProxyType({})
    RARITY_MAPPING = MappingProxyType(
        {
            "common": "common",
            "uncommon": "uncommon",
            "rare": "rare",
            "double rare": "hits",
            "ultra rare": "hits",
            "illustration rare": "hits",
            "special illustration rare": "hits",
            "hyper rare": "hits",
            "ace spec rare": "hits",
            "poke ball pattern": "hits",
            "master ball pattern": "hits",
        }
    )
    RARE_SLOT_PROBABILITY = {"rare": 1.0}
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {"regular reverse": 1.0},
        "slot_2": {"master ball pattern": 1 / 20, "regular reverse": 19 / 20},
    }

    @staticmethod
    def get_rarity_pack_multiplier():
        return {"common": 4, "uncommon": 3}


def _row(name: str, rarity: str, special_type: str, *, price: float = 1.0) -> dict:
    return {
        "Card Name": name,
        "Rarity": rarity,
        "Special Type": special_type,
        "Price ($)": float(price),
        "Reverse Variant Price ($)": 0.25,
    }


def test_common_master_ball_overlay_not_in_base_common_pool_and_in_pattern_path() -> None:
    df = pd.DataFrame([_row("Common Overlay", "common", "master ball")])
    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    assert pools["common"].empty
    assert "Common Overlay" in pools["hit"]["Card Name"].tolist()

    resolved, _ = resolve_hit_pool_rows(pools["hit"], "master ball pattern", mode="pattern")
    assert "Common Overlay" in resolved["Card Name"].tolist()


def test_rare_pokeball_overlay_not_in_base_rare_pool_and_resolves_pattern_path() -> None:
    df = pd.DataFrame([_row("Rare Overlay", "rare", "poke ball")])
    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    assert pools["rare"].empty
    assert "Rare Overlay" in pools["hit"]["Card Name"].tolist()

    resolved, _ = resolve_hit_pool_rows(pools["hit"], "poke ball pattern", mode="pattern")
    assert "Rare Overlay" in resolved["Card Name"].tolist()


def test_pattern_pull_rate_logic_uses_structured_special_type_not_card_name() -> None:
    calculator = PackEVCalculator(_PatternMathConfig())
    df = pd.DataFrame(
        [
            {
                "Card Name": "Neutral Name",
                "Rarity": "common",
                "Special Type": "master ball",
                "Price ($)": 10.0,
                "Pull Rate (1/X)": 20.0,
                "Pack Price": 5.0,
            },
            {
                "Card Name": "Master Ball Named But Not Overlay",
                "Rarity": "common",
                "Special Type": "",
                "Price ($)": 10.0,
                "Pull Rate (1/X)": 20.0,
                "Pack Price": 5.0,
            },
        ]
    )

    prepared, _ = calculator.load_and_prepare_data(df)

    overlay_row = prepared[prepared["Card Name"] == "Neutral Name"].iloc[0]
    non_overlay_row = prepared[prepared["Card Name"] == "Master Ball Named But Not Overlay"].iloc[0]

    assert overlay_row["pattern_key"] == "master_ball_pattern"
    assert overlay_row["Effective_Pull_Rate"] == pytest.approx(20.0)
    assert non_overlay_row["pattern_key"] == ""
    assert non_overlay_row["Effective_Pull_Rate"] == pytest.approx(5.0)


def test_recognized_pattern_rows_cannot_be_sampled_through_base_and_pattern_paths() -> None:
    df = pd.DataFrame(
        [
            _row("Regular Common", "common", ""),
            _row("Regular Rare", "rare", ""),
            _row("Pattern Poke", "rare", "poke ball"),
            _row("Pattern Master", "common", "master ball"),
        ]
    )
    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)
    source_pattern_keys, _ = get_row_match_keys(df, mode="pattern")

    base_indices = (
        set(pools["common"].index.tolist())
        | set(pools["uncommon"].index.tolist())
        | set(pools["rare"].index.tolist())
    )
    pattern_indices = set(df.index[source_pattern_keys.ne("")].tolist())
    hit_indices = set(pools["hit"].index.tolist())

    assert len(base_indices & pattern_indices) == 0
    assert pattern_indices.issubset(hit_indices)


def test_pattern_ev_sanity_matches_event_probability_times_pool_average() -> None:
    calculator = PackEVCalculator(_PatternMathConfig())

    master_ball_values = [7.5] * 66 + [10.04]
    assert sum(master_ball_values) == pytest.approx(505.04)

    rows = [
        {
            "Card Name": f"Master Overlay {i + 1}",
            "Rarity": "rare",
            "Special Type": "master ball",
            "Price ($)": float(value),
            "Pull Rate (1/X)": 20.0,
            "Pack Price": 5.0,
        }
        for i, value in enumerate(master_ball_values)
    ]

    prepared, _ = calculator.load_and_prepare_data(pd.DataFrame(rows))
    master_ev = float(prepared.loc[prepared["pattern_key"] == "master_ball_pattern", "EV"].sum())

    expected_ev = (505.04 / 67.0) * (1.0 / 20.0)
    assert master_ev == pytest.approx(expected_ev, rel=1e-9, abs=1e-9)
    assert master_ev < 1.0
