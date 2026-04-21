from collections import defaultdict
from typing import List, Dict, Any, Tuple

import numpy as np
import pandas as pd

from backend.calculations.packCalcsRefractored.evrCalculator import PackEVCalculator
from backend.calculations.packCalcsRefractored.packCalculationOrchestrator import (
    PackCalculationOrchestrator,
)
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import (
    SetPrismaticEvolutionsConfig,
)
from backend.simulations.monteCarloSimV2 import make_simulate_pack_fn_v2, run_simulation_v2
from backend.simulations.utils.extractScarletAndVioletCardGroups import (
    extract_scarletandviolet_card_groups,
)
from backend.simulations.utils.simulationTokenResolver import get_row_match_keys


class _PrismaticNoSpecialConfig(SetPrismaticEvolutionsConfig):
    GOD_PACK_CONFIG = {"enabled": False, "pull_rate": 0.0, "strategy": {}}
    DEMI_GOD_PACK_CONFIG = {"enabled": False, "pull_rate": 0.0, "strategy": {}}


def _add_rows(rows: List[Dict[str, Any]], rarity: str, count: int, *, price: float, pull_rate: float, special_type: str = "") -> None:
    for i in range(count):
        rows.append(
            {
                "Card Name": f"{rarity.title()} {i + 1}",
                "Rarity": rarity,
                "Special Type": special_type,
                "Price ($)": float(price),
                "Pull Rate (1/X)": float(pull_rate),
                "Reverse Variant Price ($)": 0.6 if rarity in {"common", "uncommon", "rare"} and special_type == "" else None,
                "Pack Price": 5.0,
            }
        )


def _build_prismatic_fixture() -> pd.DataFrame:
    rows: list[dict] = []
    _add_rows(rows, "common", 45, price=0.20, pull_rate=12.0)
    _add_rows(rows, "uncommon", 30, price=0.50, pull_rate=12.0)
    _add_rows(rows, "rare", 20, price=2.00, pull_rate=30.0)

    _add_rows(rows, "rare", 7, price=3.00, pull_rate=60.0, special_type="poke ball")
    _add_rows(rows, "rare", 3, price=8.00, pull_rate=120.0, special_type="master ball")

    _add_rows(rows, "double rare", 8, price=8.00, pull_rate=45.0)
    _add_rows(rows, "ultra rare", 6, price=25.0, pull_rate=65.0)
    _add_rows(rows, "illustration rare", 4, price=30.0, pull_rate=70.0)
    _add_rows(rows, "special illustration rare", 3, price=300.0, pull_rate=120.0)
    _add_rows(rows, "hyper rare", 2, price=80.0, pull_rate=150.0)
    _add_rows(rows, "ace spec rare", 2, price=6.0, pull_rate=45.0)

    return pd.DataFrame(rows)


def _run_manual_prismatic() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    orchestrator = PackCalculationOrchestrator(_PrismaticNoSpecialConfig)
    prepared_df, _ = orchestrator.load_and_prepare_data(_build_prismatic_fixture())
    manual = orchestrator.calculate_evr_calculations(prepared_df)
    return prepared_df, manual


def _run_simulation_prismatic(prepared_df: pd.DataFrame, *, n: int = 2500) -> Dict[str, Any]:
    pools = extract_scarletandviolet_card_groups(_PrismaticNoSpecialConfig, prepared_df)
    rng = np.random.default_rng(42)
    rarity_pull_counts = defaultdict(int)
    rarity_value_totals = defaultdict(float)
    simulate_one_pack = make_simulate_pack_fn_v2(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=pools["hit"],
        reverse_pool=pools["reverse"],
        slots_per_rarity=_PrismaticNoSpecialConfig.SLOTS_PER_RARITY,
        config=_PrismaticNoSpecialConfig,
        df=prepared_df,
        rarity_pull_counts=rarity_pull_counts,
        rarity_value_totals=rarity_value_totals,
        pack_logs=None,
        rng=rng,
    )
    return run_simulation_v2(
        simulate_one_pack,
        rarity_pull_counts,
        rarity_value_totals,
        n=n,
    )


def test_prismatic_manual_ev_in_reasonable_range() -> None:
    _, manual = _run_manual_prismatic()
    manual_ev = float(manual["total_manual_ev"])

    assert 15.0 < manual_ev < 25.0, (
        f"Prismatic manual EV expected in sane range (15, 25); got {manual_ev:.4f}. "
        "This guards against recurrence of inflated pattern-overlay totals like ~34.59"
    )


def test_prismatic_simulation_mean_reasonable() -> None:
    prepared_df, _ = _run_manual_prismatic()
    sim = _run_simulation_prismatic(prepared_df)
    sim_mean = float(sim["mean"])

    assert 15.0 < sim_mean < 25.0, (
        f"Prismatic simulation mean expected in sane range (15, 25); got {sim_mean:.4f}. "
        "This guards against recurrence of inflated means like ~34.79"
    )


def test_prismatic_simulation_mean_remains_directionally_aligned_with_manual_ev() -> None:
    prepared_df, manual = _run_manual_prismatic()
    sim = _run_simulation_prismatic(prepared_df, n=1500)

    manual_ev = float(manual["total_manual_ev"])
    sim_mean = float(sim["mean"])
    ratio = sim_mean / manual_ev if manual_ev else 0.0

    assert 0.65 <= ratio <= 1.35, (
        f"Prismatic simulation/manual EV ratio drifted outside guardrail: sim={sim_mean:.4f}, "
        f"manual={manual_ev:.4f}, ratio={ratio:.4f}. This is intended to catch a recurrence "
        "of base-slot overlay leakage or other major simulation/math divergence."
    )


def test_prismatic_pattern_rows_included() -> None:
    prepared_df, manual = _run_manual_prismatic()
    pokeball_rows = int(prepared_df["pattern_key"].eq("pokeball_pattern").sum())
    master_rows = int(prepared_df["pattern_key"].eq("master_ball_pattern").sum())

    assert pokeball_rows > 0, "Prismatic fixture should include pokeball_pattern rows"
    assert master_rows > 0, "Prismatic fixture should include master_ball_pattern rows"
    assert manual["ev_totals_by_rarity"].get("pokeball_pattern", 0.0) > 0.0, "pokeball_pattern EV bucket should be non-zero"
    assert manual["ev_totals_by_rarity"].get("master_ball_pattern", 0.0) > 0.0, "master_ball_pattern EV bucket should be non-zero"


def test_prismatic_pool_composition_correct() -> None:
    prepared_df, _ = _run_manual_prismatic()
    pools = extract_scarletandviolet_card_groups(_PrismaticNoSpecialConfig, prepared_df)
    hit_pattern_keys, _ = get_row_match_keys(pools["hit"], mode="pattern")

    common_size = len(pools["common"])
    pokeball_count = int(hit_pattern_keys.eq("pokeball_pattern").sum())
    master_count = int(hit_pattern_keys.eq("master_ball_pattern").sum())

    assert 40 <= common_size <= 50, f"Common base pool should be about 40-50 cards after pattern exclusion; got {common_size}"
    assert 5 <= pokeball_count <= 10, f"pokeball_pattern count should be roughly 5-10; got {pokeball_count}"
    assert 2 <= master_count <= 5, f"master_ball_pattern count should be roughly 2-5; got {master_count}"


def test_prismatic_pattern_ev_contribution_reasonable() -> None:
    _, manual = _run_manual_prismatic()
    pattern_ev_total = float(
        manual["ev_totals_by_rarity"].get("pokeball_pattern", 0.0)
        + manual["ev_totals_by_rarity"].get("master_ball_pattern", 0.0)
    )

    assert pattern_ev_total > 0.0, "Pattern EV total should be non-zero when pattern rows exist"
    assert pattern_ev_total < 5.0, (
        f"Pattern EV total should remain modest (<5). Got {pattern_ev_total:.4f}; "
        "large values suggest overlap/double-counting"
    )


def test_prismatic_gold_pack_ev_reasonable() -> None:
    fixed_cards = SetPrismaticEvolutionsConfig.GOD_PACK_CONFIG["strategy"]["cards"]
    rows: list[dict] = []

    for spec in fixed_cards:
        is_sir = str(spec.get("rarity", "")).strip().lower() == "special illustration rare"
        rows.append(
            {
                "Card Name": spec["name"],
                "Card Number": spec.get("number", ""),
                "Rarity": spec["rarity"],
                "Special Type": spec.get("special_type", ""),
                "Price ($)": 375.0 if is_sir else 25.0,
            }
        )

    for i in range(29):
        rows.append(
            {
                "Card Name": f"Extra Common {i + 1}",
                "Card Number": f"C-{i + 1}",
                "Rarity": "common",
                "Special Type": "",
                "Price ($)": 1.0,
            }
        )
    for i in range(20):
        rows.append(
            {
                "Card Name": f"Extra Uncommon {i + 1}",
                "Card Number": f"U-{i + 1}",
                "Rarity": "uncommon",
                "Special Type": "",
                "Price ($)": 2.0,
            }
        )
    for i in range(20):
        rows.append(
            {
                "Card Name": f"Extra SIR {i + 1}",
                "Card Number": f"S-{i + 1}",
                "Rarity": "special illustration rare",
                "Special Type": "",
                "Price ($)": 20.0,
            }
        )

    df = pd.DataFrame(rows)
    calculator = PackEVCalculator(SetPrismaticEvolutionsConfig)
    contrib = calculator.calculate_god_packs_ev_contributions(df)

    assert 1.5 < float(contrib["god_pack_ev"]) < 1.9, (
        f"God pack EV should stay near historical expectation (~1.7). Got {contrib['god_pack_ev']:.4f}"
    )
    assert 0.45 < float(contrib["demi_god_pack_ev"]) < 0.75, (
        f"Demi-god EV should stay near historical expectation (~0.6). Got {contrib['demi_god_pack_ev']:.4f}"
    )
