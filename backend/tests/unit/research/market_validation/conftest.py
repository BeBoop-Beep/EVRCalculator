from __future__ import annotations

import math
import random
from typing import Any, Dict, List

import pytest


def _synthetic_card_records(n_sets: int = 12, cards_per_set: int = 15, seed: int = 42) -> List[Dict[str, Any]]:
    """Deterministic synthetic dataset: pokemon_subject_appeal genuinely drives
    log_market_price (with noise + a set-level random effect and an era control),
    trainer_appeal is pure noise (no relationship), so the harness's own tests can
    assert it recovers the right qualitative answer for each."""
    rng = random.Random(seed)
    eras = ["scarlet_violet", "sword_shield", "sun_moon"]
    records: List[Dict[str, Any]] = []
    for s in range(n_sets):
        set_id = f"set_{s}"
        era = eras[s % len(eras)]
        set_effect = rng.uniform(-0.3, 0.3)
        for c in range(cards_per_set):
            appeal = rng.uniform(40, 100)
            trainer_appeal = rng.uniform(0, 100)  # unrelated to price by construction
            noise = rng.gauss(0, 0.4)
            log_price = 1.0 + 0.02 * (appeal - 50) + set_effect + noise
            price = math.exp(log_price)
            records.append(
                {
                    "canonical_card_id": f"{set_id}_card_{c}",
                    "set_id": set_id,
                    "era": era,
                    "set_era_bucket": era,
                    "supertype": "Pokemon" if c % 4 != 0 else "Trainer",
                    "market_price": price,
                    "log_market_price": log_price,
                    "pokemon_subject_appeal": appeal,
                    "trainer_appeal": trainer_appeal,
                    "release_age_days": 200 + s * 10,
                    "rarity": "Rare" if c % 3 == 0 else "Common",
                    "collector_model_version": "fixture_v1",
                    "collector_model_run_id": "fixture-run-1",
                    "final_card_collector_appeal": appeal,
                }
            )
    return records


@pytest.fixture()
def synthetic_card_records() -> List[Dict[str, Any]]:
    return _synthetic_card_records()


@pytest.fixture()
def synthetic_card_records_factory():
    return _synthetic_card_records
