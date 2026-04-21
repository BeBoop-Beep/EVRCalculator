from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd

from backend.calculations.packCalcsRefractored.packCalculationOrchestrator import (
    PackCalculationOrchestrator,
)
from backend.constants.tcg.pokemon.scarletAndVioletEra.obsidianFlames import (
    SetObsidianFlamesConfig,
)
from backend.simulations.monteCarloSimV2 import make_simulate_pack_fn_v2, run_simulation_v2
from backend.simulations.utils.extractScarletAndVioletCardGroups import (
    extract_scarletandviolet_card_groups,
)


def _add_rows(rows: List[Dict[str, Any]], rarity: str, count: int, *, price: float, pull_rate: float, label_prefix: Optional[str] = None) -> None:
    prefix = label_prefix or rarity.title()
    for i in range(count):
        rows.append(
            {
                "Card Name": f"{prefix} {i + 1}",
                "Rarity": rarity,
                "Special Type": "",
                "Price ($)": float(price),
                "Pull Rate (1/X)": float(pull_rate),
                "Reverse Variant Price ($)": 0.45 if rarity in {"common", "uncommon", "rare"} else None,
                "Pack Price": 5.0,
            }
        )


def _build_obsidian_fixture() -> pd.DataFrame:
    rows: list[dict] = []
    _add_rows(rows, "common", 40, price=0.15, pull_rate=20.0)
    _add_rows(rows, "uncommon", 30, price=0.30, pull_rate=18.0)
    _add_rows(rows, "rare", 18, price=1.6, pull_rate=15.0)
    _add_rows(rows, "double rare", 8, price=5.5, pull_rate=40.0)
    _add_rows(rows, "ultra rare", 4, price=12.0, pull_rate=80.0)
    _add_rows(rows, "illustration rare", 6, price=9.0, pull_rate=70.0)
    _add_rows(rows, "special illustration rare", 2, price=25.0, pull_rate=130.0)
    _add_rows(rows, "hyper rare", 2, price=30.0, pull_rate=120.0)

    rows.append(
        {
            "Card Name": "Master Ball Promo Name Only",
            "Rarity": "common",
            "Special Type": "",
            "Price ($)": 0.20,
            "Pull Rate (1/X)": 20.0,
            "Reverse Variant Price ($)": 0.45,
            "Pack Price": 5.0,
        }
    )
    return pd.DataFrame(rows)


def _run_obsidian_manual() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    orchestrator = PackCalculationOrchestrator(SetObsidianFlamesConfig)
    prepared_df, _ = orchestrator.load_and_prepare_data(_build_obsidian_fixture())
    manual = orchestrator.calculate_evr_calculations(prepared_df)
    return prepared_df, manual


def _run_obsidian_sim(prepared_df: pd.DataFrame, *, n: int = 1800) -> Dict[str, Any]:
    pools = extract_scarletandviolet_card_groups(SetObsidianFlamesConfig, prepared_df)
    rarity_pull_counts = defaultdict(int)
    rarity_value_totals = defaultdict(float)
    simulate_one_pack = make_simulate_pack_fn_v2(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=pools["hit"],
        reverse_pool=pools["reverse"],
        slots_per_rarity=SetObsidianFlamesConfig.SLOTS_PER_RARITY,
        config=SetObsidianFlamesConfig,
        df=prepared_df,
        rarity_pull_counts=rarity_pull_counts,
        rarity_value_totals=rarity_value_totals,
        pack_logs=[],
        rng=np.random.default_rng(7),
    )
    return run_simulation_v2(
        lambda: simulate_one_pack(return_pack_data=True),
        rarity_pull_counts,
        rarity_value_totals,
        n=n,
    )


def test_obsidian_flames_unchanged() -> None:
    prepared_df, _ = _run_obsidian_manual()
    pools = extract_scarletandviolet_card_groups(SetObsidianFlamesConfig, prepared_df)

    assert int(prepared_df["pattern_key"].ne("").sum()) == 0, "Non-pattern fixture should have zero detected pattern rows"
    assert len(pools["common"]) > 0, "Common pool should be populated for non-pattern set"
    assert len(pools["uncommon"]) > 0, "Uncommon pool should be populated for non-pattern set"
    assert len(pools["rare"]) > 0, "Rare pool should be populated for non-pattern set"
    assert len(pools["hit"]) > 0, "Hit pool should still include hit rarities in non-pattern set"
    assert len(pools["reverse"]) > 0, "Reverse pool should be available for non-pattern set"


def test_obsidian_flames_manual_ev_unchanged() -> None:
    _, manual = _run_obsidian_manual()
    manual_ev = float(manual["total_manual_ev"])

    assert np.isfinite(manual_ev), "Manual EV should compute to a finite number for non-pattern sets"
    assert manual_ev > 0.0, "Manual EV should remain positive for non-pattern sets"


def test_obsidian_flames_simulation_completes() -> None:
    prepared_df, _ = _run_obsidian_manual()
    sim = _run_obsidian_sim(prepared_df)

    assert np.isfinite(float(sim["mean"])), "Simulation mean should be finite for non-pattern sets"
    assert 5.0 < float(sim["mean"]) < 20.0, (
        f"Simulation mean for non-pattern fixture should stay in reasonable range; got {sim['mean']:.4f}"
    )


def test_non_pattern_pull_rate_unchanged() -> None:
    prepared_df, _ = _run_obsidian_manual()

    common_rate = float(prepared_df.loc[prepared_df["Rarity"].eq("common"), "Effective_Pull_Rate"].iloc[0])
    uncommon_rate = float(prepared_df.loc[prepared_df["Rarity"].eq("uncommon"), "Effective_Pull_Rate"].iloc[0])
    rare_rate = float(prepared_df.loc[prepared_df["Rarity"].eq("rare"), "Effective_Pull_Rate"].iloc[0])

    assert common_rate == 20.0 / 4.0, "Common pull-rate path should remain guaranteed-slot /4"
    assert uncommon_rate == 18.0 / 3.0, "Uncommon pull-rate path should remain guaranteed-slot /3"

    expected_rare = 1.0 / (SetObsidianFlamesConfig.RARE_SLOT_PROBABILITY["rare"] * (1.0 / 15.0))
    assert rare_rate == expected_rare, "Rare pull-rate path should remain probability-based"


def test_pattern_detection_false_positives() -> None:
    prepared_df, _ = _run_obsidian_manual()

    false_positive_rows = prepared_df[
        prepared_df["Card Name"].str.contains("Master Ball", case=False, na=False)
        & prepared_df["pattern_key"].ne("")
    ]
    assert false_positive_rows.empty, (
        "Card name substrings like 'Master Ball' must not trigger pattern detection in non-pattern sets"
    )
    assert int(prepared_df["pattern_key"].ne("").sum()) == 0, "Expected exactly zero detected pattern rows in non-pattern fixture"
