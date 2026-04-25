import pandas as pd
from typing import Tuple, Dict, Any, Set
from collections import defaultdict

from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import (
    SetPrismaticEvolutionsConfig,
)
from backend.simulations.utils.extractScarletAndVioletCardGroups import (
    extract_scarletandviolet_card_groups,
)


def _fixture_df() -> pd.DataFrame:
    rows = [
        {
            "Card Name": "C1",
            "Rarity": "common",
            "Special Type": "",
            "Price ($)": 0.2,
            "Reverse Variant Price ($)": 0.1,
        },
        {
            "Card Name": "U1",
            "Rarity": "uncommon",
            "Special Type": "",
            "Price ($)": 0.3,
            "Reverse Variant Price ($)": 0.15,
        },
        {
            "Card Name": "R1",
            "Rarity": "rare",
            "Special Type": "",
            "Price ($)": 1.0,
            "Reverse Variant Price ($)": 0.25,
        },
        {
            "Card Name": "PatternP",
            "Rarity": "rare",
            "Special Type": "poke ball",
            "Price ($)": 2.0,
            "Reverse Variant Price ($)": 0.2,
        },
        {
            "Card Name": "PatternM",
            "Rarity": "rare",
            "Special Type": "master ball",
            "Price ($)": 4.0,
            "Reverse Variant Price ($)": 0.2,
        },
        {
            "Card Name": "IR1",
            "Rarity": "illustration rare",
            "Special Type": "",
            "Price ($)": 8.0,
            "Reverse Variant Price ($)": None,
        },
    ]
    return pd.DataFrame(rows)


def _extract() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    df = _fixture_df()
    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)
    return df, pools


def _idx(pool: pd.DataFrame) -> Set[int]:
    return set(pool.index.tolist())


def test_base_pools_mutually_exclusive() -> None:
    _, pools = _extract()
    common_idx = _idx(pools["common"])
    uncommon_idx = _idx(pools["uncommon"])
    rare_idx = _idx(pools["rare"])

    assert common_idx.isdisjoint(uncommon_idx), "Common and uncommon pools must be mutually exclusive"
    assert common_idx.isdisjoint(rare_idx), "Common and rare pools must be mutually exclusive"
    assert uncommon_idx.isdisjoint(rare_idx), "Uncommon and rare pools must be mutually exclusive"


def test_non_pattern_base_rows_exclude_from_hit_pool() -> None:
    _, pools = _extract()
    base_idx = _idx(pools["common"]) | _idx(pools["uncommon"]) | _idx(pools["rare"])
    hit_idx = _idx(pools["hit"])

    non_pattern_base_idx = {0, 1, 2}
    assert non_pattern_base_idx.isdisjoint(hit_idx), "Non-pattern base rows must not also appear in hit pool"
    assert 5 in hit_idx, "Hit-rarity rows should still be present in hit pool"


def test_pattern_pool_does_not_overlap_with_base() -> None:
    _, pools = _extract()
    base_idx = _idx(pools["common"]) | _idx(pools["uncommon"]) | _idx(pools["rare"])
    hit_idx = _idx(pools["hit"])
    pattern_idx = {3, 4}

    assert pattern_idx.issubset(hit_idx), "Pattern rows must be in hit pool"
    assert pattern_idx.isdisjoint(base_idx), "Pattern rows must not overlap with any base pool (common/uncommon/rare)"


def test_no_row_in_multiple_base_pool_types() -> None:
    _, pools = _extract()
    pool_indices = {
        "common": _idx(pools["common"]),
        "uncommon": _idx(pools["uncommon"]),
        "rare": _idx(pools["rare"]),
    }

    seen: dict[int, str] = {}
    for pool_name, indices in pool_indices.items():
        for row_index in indices:
            assert row_index not in seen, (
                f"Row index {row_index} appeared in both {seen[row_index]} and {pool_name}; "
                "every source row must map to exactly one base rarity pool"
            )
            seen[row_index] = pool_name


def test_all_rows_accounted_for() -> None:
    df, pools = _extract()
    accounted = _idx(pools["common"]) | _idx(pools["uncommon"]) | _idx(pools["rare"]) | _idx(pools["hit"])
    source = set(df.index.tolist())

    assert accounted == source, (
        "Every source row must be represented in at least one of common/uncommon/rare/hit pools. "
        f"Missing={sorted(source - accounted)} Extra={sorted(accounted - source)}"
    )
