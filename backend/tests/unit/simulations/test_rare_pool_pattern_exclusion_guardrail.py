import pandas as pd

from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import (
    SetPrismaticEvolutionsConfig,
)
from backend.simulations.utils.extractScarletAndVioletCardGroups import (
    extract_scarletandviolet_card_groups,
)


def _extract(df: pd.DataFrame) -> dict:
    return extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)


def test_rare_pool_contains_poke_ball_pattern_row() -> None:
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

    assert "Rare Poke Pattern" in pools["rare"]["Card Name"].tolist()
    assert "Rare Poke Pattern" in pools["hit"]["Card Name"].tolist()


def test_rare_pool_contains_master_ball_pattern_row() -> None:
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

    assert "Rare Master Pattern" in pools["rare"]["Card Name"].tolist()
    assert "Rare Master Pattern" in pools["hit"]["Card Name"].tolist()


def test_rare_pool_preserves_all_base_rare_rows() -> None:
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

    assert rare_names == {"Normal Rare", "Pattern Poke A", "Pattern Master B"}
