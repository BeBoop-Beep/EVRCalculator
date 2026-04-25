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


def test_common_overlay_row_excluded_from_common_base_pool_and_present_in_hit_pool() -> None:
    df = pd.DataFrame(
        [
            _build_row("Common Poke Overlay", "Common", "poke_ball_pattern"),
            _build_row("Common Plain", "Common", ""),
        ]
    )

    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    # Pattern overlay rows must NOT appear in the base common pool.
    assert "Common Poke Overlay" not in pools["common"]["Card Name"].tolist()
    # Plain rows must remain in the common pool.
    assert "Common Plain" in pools["common"]["Card Name"].tolist()
    # Pattern overlay rows must be present in the hit pool.
    assert "Common Poke Overlay" in pools["hit"]["Card Name"].tolist()


def test_uncommon_overlay_row_excluded_from_uncommon_base_pool_and_present_in_hit_pool() -> None:
    df = pd.DataFrame(
        [
            _build_row("Uncommon Poke Overlay", "Uncommon", "poke_ball_pattern"),
            _build_row("Uncommon Plain", "Uncommon", ""),
        ]
    )

    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    # Pattern overlay rows must NOT appear in the base uncommon pool.
    assert "Uncommon Poke Overlay" not in pools["uncommon"]["Card Name"].tolist()
    # Plain rows must remain in the uncommon pool.
    assert "Uncommon Plain" in pools["uncommon"]["Card Name"].tolist()
    # Pattern overlay rows must be present in the hit pool.
    assert "Uncommon Poke Overlay" in pools["hit"]["Card Name"].tolist()


def test_rare_overlay_row_excluded_from_rare_base_pool_and_present_in_hit_pool() -> None:
    df = pd.DataFrame(
        [
            _build_row("Rare Master Overlay", "Rare", "master_ball_pattern"),
            _build_row("Rare Plain", "Rare", ""),
        ]
    )

    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    # Pattern overlay rows must NOT appear in the base rare pool.
    assert "Rare Master Overlay" not in pools["rare"]["Card Name"].tolist()
    # Plain rows must remain in the rare pool.
    assert "Rare Plain" in pools["rare"]["Card Name"].tolist()
    # Pattern overlay rows must be present in the hit pool.
    assert "Rare Master Overlay" in pools["hit"]["Card Name"].tolist()


def test_overlay_rows_excluded_from_base_pools_with_no_row_duplication() -> None:
    df = pd.DataFrame(
        [
            _build_row("Common Overlay", "Common", "poke_ball_pattern"),
            _build_row("Uncommon Overlay", "Uncommon", "poke_ball_pattern"),
            _build_row("Rare Overlay", "Rare", "master_ball_pattern"),
        ]
    )

    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    # All rows are pattern overlays, so base pools must be empty.
    assert len(pools["common"]) == 0
    assert len(pools["uncommon"]) == 0
    assert len(pools["rare"]) == 0

    # All pattern overlay rows must appear in the hit pool.
    assert len(pools["hit"]) == 3

    # No physical row duplication is introduced in any individual pool view.
    for pool_name in ("common", "uncommon", "rare", "hit"):
        pool_df = pools[pool_name]
        if "__source_row_index__" in pool_df.columns:
            assert pool_df["__source_row_index__"].is_unique
