from types import MappingProxyType
from typing import Tuple, Dict, Any

import pandas as pd
import pytest

from backend.calculations.packCalcsRefractored.packCalculationOrchestrator import (
    PackCalculationOrchestrator,
)


class _ManualParityConfig:
    RARITY_MAPPING = MappingProxyType(
        {
            "common": "common",
            "uncommon": "uncommon",
            "rare": "rare",
            "double rare": "hits",
            "ultra rare": "hits",
            "hyper rare": "hits",
            "illustration rare": "hits",
            "special illustration rare": "hits",
            "ace spec rare": "hits",
            "poke ball pattern": "hits",
            "master ball pattern": "hits",
        }
    )
    PULL_RATE_MAPPING = MappingProxyType({})
    RARE_SLOT_PROBABILITY = {"double rare": 0.2, "rare": 0.8}
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {"regular reverse": 1.0},
        "slot_2": {"regular reverse": 1.0},
    }
    GOD_PACK_CONFIG = {"enabled": False}
    DEMI_GOD_PACK_CONFIG = {"enabled": False}

    @staticmethod
    def get_rarity_pack_multiplier():
        return {"common": 4, "uncommon": 3}

    @staticmethod
    def get_reverse_eligible_rarities():
        return ["common", "uncommon", "rare"]


def _build_raw_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Card Name": "Common A",
                "Rarity": "common",
                "Special Type": "",
                "Price ($)": 0.40,
                "Pull Rate (1/X)": 20.0,
                "Reverse Variant Price ($)": 0.20,
                "Pack Price": 5.0,
            },
            {
                "Card Name": "Uncommon A",
                "Rarity": "uncommon",
                "Special Type": "",
                "Price ($)": 0.90,
                "Pull Rate (1/X)": 30.0,
                "Reverse Variant Price ($)": 0.30,
                "Pack Price": 5.0,
            },
            {
                "Card Name": "Rare A",
                "Rarity": "rare",
                "Special Type": "",
                "Price ($)": 3.00,
                "Pull Rate (1/X)": 40.0,
                "Reverse Variant Price ($)": 0.40,
                "Pack Price": 5.0,
            },
            {
                "Card Name": "Poke Pattern A",
                "Rarity": "rare",
                "Special Type": "poke ball",
                "Price ($)": 5.00,
                "Pull Rate (1/X)": 120.0,
                "Reverse Variant Price ($)": 1.0,
                "Pack Price": 5.0,
            },
            {
                "Card Name": "Master Pattern A",
                "Rarity": "rare",
                "Special Type": "master ball",
                "Price ($)": 9.00,
                "Pull Rate (1/X)": 300.0,
                "Reverse Variant Price ($)": 1.0,
                "Pack Price": 5.0,
            },
            {
                "Card Name": "Ace Spec A",
                "Rarity": "ace spec rare",
                "Special Type": "",
                "Price ($)": 7.00,
                "Pull Rate (1/X)": 80.0,
                "Reverse Variant Price ($)": None,
                "Pack Price": 5.0,
            },
            {
                "Card Name": "Illustration Rare A",
                "Rarity": "illustration rare",
                "Special Type": "",
                "Price ($)": 12.00,
                "Pull Rate (1/X)": 100.0,
                "Reverse Variant Price ($)": None,
                "Pack Price": 5.0,
            },
        ]
    )


def _run_manual() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    orchestrator = PackCalculationOrchestrator(_ManualParityConfig())
    prepared_df, _ = orchestrator.load_and_prepare_data(_build_raw_df())
    result = orchestrator.calculate_evr_calculations(prepared_df)
    return prepared_df, result


def test_row_ev_sum_equals_bucket_totals() -> None:
    prepared_df, result = _run_manual()
    ev_totals = result["ev_totals_by_rarity"]

    row_ev_sum = float(prepared_df["EV"].sum())
    bucket_sum_excluding_reverse = sum(v for k, v in ev_totals.items() if k != "reverse")

    assert bucket_sum_excluding_reverse == pytest.approx(row_ev_sum, abs=1e-9), (
        "Row-level EV sum must reconcile exactly with bucket totals excluding reverse"
    )
    for required_bucket in [
        "common",
        "uncommon",
        "rare",
        "pokeball_pattern",
        "master_ball_pattern",
        "ace_spec_rare",
        "illustration_rare",
        "reverse",
    ]:
        assert required_bucket in ev_totals, f"Expected EV bucket '{required_bucket}' to be present"


def test_pattern_bucket_parity() -> None:
    prepared_df, result = _run_manual()
    ev_totals = result["ev_totals_by_rarity"]

    pattern_rows_ev = float(prepared_df.loc[prepared_df["pattern_key"].ne(""), "EV"].sum())
    pattern_bucket_ev = float(ev_totals.get("pokeball_pattern", 0.0) + ev_totals.get("master_ball_pattern", 0.0))

    assert pattern_rows_ev == pytest.approx(pattern_bucket_ev, abs=1e-9), (
        "Pattern EV parity failed: sum(pattern rows) must equal pokeball+master pattern buckets"
    )


def test_no_double_counting_across_buckets() -> None:
    prepared_df, result = _run_manual()
    ev_totals = result["ev_totals_by_rarity"]

    grouped = (
        prepared_df.assign(_ev=prepared_df["EV"].astype(float))
        .groupby("aggregation_key")["_ev"]
        .sum()
        .to_dict()
    )
    for bucket, bucket_total in ev_totals.items():
        if bucket == "reverse":
            continue
        assert bucket in grouped, f"Bucket '{bucket}' exists in totals but has no source aggregation rows"
        assert bucket_total == pytest.approx(grouped[bucket], abs=1e-9), (
            f"Bucket '{bucket}' total does not match grouped row EV, indicating possible overlap or leakage"
        )


def test_reverse_bucket_separate() -> None:
    prepared_df, result = _run_manual()
    reverse_total = float(result["ev_totals_by_rarity"]["reverse"])

    # Reverse EV should come from reverse prices (not Price ($)): slot_1+slot_2 are both 100% regular reverse.
    expected_reverse_total = 2.0 * float(prepared_df.loc[[0, 1, 2], "Reverse Variant Price ($)"].astype(float).mean())
    assert reverse_total == pytest.approx(expected_reverse_total, abs=1e-9), (
        "Reverse EV bucket must be derived from Reverse Variant Price ($) and reverse slot probabilities"
    )

    price_based_total = 2.0 * float(prepared_df.loc[[0, 1, 2], "Price ($)"].astype(float).mean())
    assert reverse_total != pytest.approx(price_based_total), (
        "Reverse EV should not be derived from base Price ($); this guards reverse/base confusion regressions"
    )
