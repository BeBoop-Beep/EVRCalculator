import pandas as pd

from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import (
    SetPrismaticEvolutionsConfig,
)
from backend.simulations.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups


BASE_ROW = {
    "Set Name": "Prismatic Evolutions",
    "EV": 1.0,
    "Price ($)": 1.0,
    "Reverse Variant Price ($)": 1.0,
}


def _build_row(card_name: str, rarity: str, pattern: str = "") -> dict:
    row = dict(BASE_ROW)
    row.update({"Card Name": card_name, "Rarity": rarity, "pattern_key": pattern})
    return row


def test_common_overlay_row_stays_in_common_base_pool_and_hit_pool() -> None:
    df = pd.DataFrame(
        [
            _build_row("Common Poke Overlay", "Common", "poke_ball_pattern"),
            _build_row("Common Plain", "Common", ""),
        ]
    )

    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    assert "Common Poke Overlay" in pools["common"]["Card Name"].tolist()
    assert "Common Poke Overlay" in pools["hit"]["Card Name"].tolist()


def test_uncommon_overlay_row_stays_in_uncommon_base_pool_and_hit_pool() -> None:
    df = pd.DataFrame(
        [
            _build_row("Uncommon Poke Overlay", "Uncommon", "poke_ball_pattern"),
            _build_row("Uncommon Plain", "Uncommon", ""),
        ]
    )

    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    assert "Uncommon Poke Overlay" in pools["uncommon"]["Card Name"].tolist()
    assert "Uncommon Poke Overlay" in pools["hit"]["Card Name"].tolist()


def test_rare_overlay_row_stays_in_rare_base_pool_and_hit_pool() -> None:
    df = pd.DataFrame(
        [
            _build_row("Rare Master Overlay", "Rare", "master_ball_pattern"),
            _build_row("Rare Plain", "Rare", ""),
        ]
    )

    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    assert "Rare Master Overlay" in pools["rare"]["Card Name"].tolist()
    assert "Rare Master Overlay" in pools["hit"]["Card Name"].tolist()


def test_overlay_rows_preserve_dual_identity_without_row_duplication() -> None:
    df = pd.DataFrame(
        [
            _build_row("Common Overlay", "Common", "poke_ball_pattern"),
            _build_row("Uncommon Overlay", "Uncommon", "poke_ball_pattern"),
            _build_row("Rare Overlay", "Rare", "master_ball_pattern"),
        ]
    )

    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    # Common + uncommon + rare base pools should each keep their rarity member.
    assert len(pools["common"]) == 1
    assert len(pools["uncommon"]) == 1
    assert len(pools["rare"]) == 1

    # No physical row duplication is introduced in any individual pool view.
    for pool_name in ("common", "uncommon", "rare", "hit"):
        pool_df = pools[pool_name]
        if "__source_row_index__" in pool_df.columns:
            assert pool_df["__source_row_index__"].is_unique
