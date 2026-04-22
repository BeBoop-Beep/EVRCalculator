import pandas as pd

from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import (
    SetPrismaticEvolutionsConfig,
)
from backend.simulations.utils.extractScarletAndVioletCardGroups import (
    extract_scarletandviolet_card_groups,
)


def _extract(df: pd.DataFrame) -> dict:
    return extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)


def test_rare_pool_excludes_poke_ball_pattern_row_which_lands_in_hit_pool() -> None:
    df = pd.DataFrame(
        [
            {
                "Card Name": "Rare Poke Pattern",
                "Rarity": "rare",
                "Special Type": "poke_ball",
                "Price ($)": 2.0,
                "Reverse Variant Price ($)": 0.2,
            }
        ]
    )
    pools = _extract(df)

    # Pattern rows must NOT appear in the base rare pool.
    assert "Rare Poke Pattern" not in pools["rare"]["Card Name"].tolist()
    # Pattern rows must be present in the hit pool.
    assert "Rare Poke Pattern" in pools["hit"]["Card Name"].tolist()


def test_rare_pool_excludes_master_ball_pattern_row_which_lands_in_hit_pool() -> None:
    df = pd.DataFrame(
        [
            {
                "Card Name": "Rare Master Pattern",
                "Rarity": "rare",
                "Special Type": "master_ball",
                "Price ($)": 3.0,
                "Reverse Variant Price ($)": 0.2,
            }
        ]
    )
    pools = _extract(df)

    # Pattern rows must NOT appear in the base rare pool.
    assert "Rare Master Pattern" not in pools["rare"]["Card Name"].tolist()
    # Pattern rows must be present in the hit pool.
    assert "Rare Master Pattern" in pools["hit"]["Card Name"].tolist()


def test_rare_pool_contains_only_non_pattern_rows() -> None:
    df = pd.DataFrame(
        [
            {
                "Card Name": "Normal Rare",
                "Rarity": "rare",
                "Special Type": "",
                "Price ($)": 1.0,
                "Reverse Variant Price ($)": 0.2,
            },
            {
                "Card Name": "Pattern Poke A",
                "Rarity": "rare",
                "Special Type": "poke ball",
                "Price ($)": 2.0,
                "Reverse Variant Price ($)": 0.2,
            },
            {
                "Card Name": "Pattern Master B",
                "Rarity": "rare",
                "Special Type": "master ball",
                "Price ($)": 2.5,
                "Reverse Variant Price ($)": 0.2,
            },
        ]
    )
    pools = _extract(df)
    rare_names = set(pools["rare"]["Card Name"].tolist())

    # Only plain (non-pattern) rare rows should be in the rare base pool.
    assert rare_names == {"Normal Rare"}
    # Pattern rows must be excluded from the rare pool and present in hit pool.
    assert "Pattern Poke A" not in rare_names
    assert "Pattern Master B" not in rare_names
    assert "Pattern Poke A" in pools["hit"]["Card Name"].tolist()
    assert "Pattern Master B" in pools["hit"]["Card Name"].tolist()
