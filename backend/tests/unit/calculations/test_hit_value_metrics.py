from types import MappingProxyType

import pandas as pd
import pytest

from backend.calculations.evr.hit_value_metrics import (
    compute_hit_value_metrics,
    compute_simulated_set_value,
)


class _Config:
    RARITY_MAPPING = MappingProxyType(
        {
            "common": "common",
            "uncommon": "uncommon",
            "rare": "rare",
            "ultra rare": "hits",
            "illustration rare": "hits",
            "special illustration rare": "hits",
            "hyper rare": "hits",
            "poke ball pattern": "hits",
            "master ball pattern": "hits",
        }
    )


def test_compute_hit_value_metrics_excludes_patterns_and_preserves_pack_ev_inputs():
    metrics = compute_hit_value_metrics(
        rarity_pull_counts={
            "common": 20,
            "ultra rare": 2,
            "special illustration rare": 1,
            "poke ball pattern": 5,
            "master ball pattern": 3,
        },
        rarity_value_totals={
            "common": 2.0,
            "ultra rare": 30.0,
            "special illustration rare": 90.0,
            "poke ball pattern": 500.0,
            "master ball pattern": 300.0,
        },
        packs_simulated=10,
        config=_Config(),
    )

    assert metrics["total_value_hit_cards_pulled"] == pytest.approx(120.0)
    assert metrics["hit_cards_pulled"] == 3
    assert metrics["average_hit_value"] == pytest.approx(40.0)
    assert metrics["hit_ev_per_pack"] == pytest.approx(12.0)
    assert metrics["hit_pull_rate"] == pytest.approx(0.3)


def test_compute_hit_value_metrics_returns_null_average_when_zero_hits():
    metrics = compute_hit_value_metrics(
        rarity_pull_counts={"common": 20, "poke ball pattern": 2},
        rarity_value_totals={"common": 2.0, "poke ball pattern": 100.0},
        packs_simulated=10,
        config=_Config(),
    )

    assert metrics["hit_cards_pulled"] == 0
    assert metrics["average_hit_value"] is None
    assert metrics["hit_ev_per_pack"] == pytest.approx(0.0)
    assert metrics["hit_pull_rate"] == pytest.approx(0.0)


def test_compute_simulated_set_value_collapses_variants_by_canonical_card_id():
    df = pd.DataFrame(
        [
            {
                "card_id": "card-1",
                "Card Name": "Bulbasaur",
                "Card Number": "001",
                "Rarity": "common",
                "Special Type": "",
                "Price ($)": 1.25,
            },
            {
                "card_id": "card-1",
                "Card Name": "Bulbasaur",
                "Card Number": "001",
                "Rarity": "common",
                "Special Type": "Poke Ball Pattern",
                "Price ($)": 10.0,
            },
            {
                "card_id": "card-2",
                "Card Name": "Ivysaur",
                "Card Number": "002",
                "Rarity": "uncommon",
                "Special Type": "",
                "Price ($)": 2.75,
            },
        ]
    )

    metrics = compute_simulated_set_value(df, config=_Config(), set_id="test-set")

    assert metrics["simulated_set_value"] == pytest.approx(4.0)
    assert metrics["simulated_set_value_card_count"] == 2


def test_compute_simulated_set_value_fallback_identity_counts_distinct_numbers():
    df = pd.DataFrame(
        [
            {"Card Name": "Pikachu", "Card Number": "025", "Rarity": "rare", "Price ($)": 3.0},
            {"Card Name": "Pikachu", "Card Number": "026", "Rarity": "rare", "Price ($)": 4.0},
            {"Card Name": "Missing Price", "Card Number": "027", "Rarity": "rare", "Price ($)": None},
        ]
    )

    metrics = compute_simulated_set_value(df, config=_Config(), set_id="test-set")

    assert metrics["simulated_set_value"] == pytest.approx(7.0)
    assert metrics["simulated_set_value_card_count"] == 2
