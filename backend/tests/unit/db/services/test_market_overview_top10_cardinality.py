from __future__ import annotations

import pytest

from backend.db.services.pokemon_market_index_service import (
    PokemonMarketIndexUnavailable,
    build_market_overview,
)
from backend.domain.pokemon.market_index import deterministic_fingerprint


DAY_1 = "2026-09-14"
DAY_2 = "2026-09-15"
SET_IDS = ["set-a", "set-b", "set-c"]
FINGERPRINT = deterministic_fingerprint(SET_IDS)


def _constituents(counts):
    return [
        {
            "setId": set_id,
            "canonicalKey": set_id,
            "setValue": 100.0 - index,
            "includedCardCount": count,
            "sourceSnapshotDate": DAY_2,
            "source": "fixture",
            "sourceUpdatedAt": f"{DAY_2}T00:00:00+00:00",
        }
        for index, (set_id, count) in enumerate(zip(SET_IDS, counts))
    ]


def _row(index_key, day, *, card_count, constituents=None, fingerprint=FINGERPRINT, set_count=3):
    return {
        "index_key": index_key,
        "market_date": day,
        "normalized_index_value": 100.0 if day == DAY_1 else 101.0,
        "basket_value": 1000.0 if index_key == "raw" else 500.0,
        "set_count": set_count,
        "card_count": card_count,
        "cohort_fingerprint": fingerprint,
        "source_generation_fingerprint": f"{index_key}-{day}",
        "constituents_json": list(constituents or []),
    }


def _history(*, chase_card_count=27, chase_counts=(10, 10, 7), fingerprint=FINGERPRINT):
    chase_constituents = _constituents(chase_counts)
    return [
        _row("raw", DAY_1, card_count=100),
        _row("top10", DAY_1, card_count=30),
        _row("raw", DAY_2, card_count=100),
        _row(
            "top10",
            DAY_2,
            card_count=chase_card_count,
            constituents=chase_constituents,
            fingerprint=fingerprint,
        ),
    ]


def test_top10_allows_fewer_than_ten_priced_cards_for_one_set():
    result = build_market_overview(_history(), market_date=DAY_2)
    assert result["coverage"]["eligibleSetCount"] == 3
    assert result["coverage"]["chaseCardCount"] == 27


def test_top10_rejects_aggregate_above_ten_cards_per_set():
    with pytest.raises(PokemonMarketIndexUnavailable, match="top10 chase card count is invalid"):
        build_market_overview(
            _history(chase_card_count=31, chase_counts=(10, 10, 10)),
            market_date=DAY_2,
        )


def test_top10_rejects_constituent_above_ten_even_when_aggregate_is_bounded():
    with pytest.raises(PokemonMarketIndexUnavailable, match="outside 1..10"):
        build_market_overview(
            _history(chase_card_count=30, chase_counts=(11, 9, 10)),
            market_date=DAY_2,
        )


def test_top10_rejects_constituent_sum_that_does_not_reconcile():
    with pytest.raises(PokemonMarketIndexUnavailable, match="do not reconcile"):
        build_market_overview(
            _history(chase_card_count=29, chase_counts=(10, 10, 7)),
            market_date=DAY_2,
        )


def test_raw_and_top10_still_require_the_same_cohort():
    with pytest.raises(PokemonMarketIndexUnavailable, match="raw/top10 cohort disagrees"):
        build_market_overview(
            _history(fingerprint=deterministic_fingerprint(["different"])),
            market_date=DAY_2,
        )
