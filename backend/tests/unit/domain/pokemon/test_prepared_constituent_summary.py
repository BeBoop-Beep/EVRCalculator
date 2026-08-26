"""The prepared current-composition contract published on each segment.

The properties that matter are honesty properties: a bounded preview must be
recognisable as one, the stated total must be the real total, the ordering must
be reproducible, and no historical observation may leak into a field whose whole
purpose is "what is in this index right now".
"""

from __future__ import annotations

import pytest

from backend.domain.pokemon.prepared_constituent_summary import (
    DEFAULT_CARD_CONSTITUENT_LIMIT,
    PREPARED_CONSTITUENT_SUMMARY_VERSION,
    summarize_card_segment_constituents,
    summarize_sealed_segment_constituents,
)


def cards(count, *, start=10000.0):
    return [
        {
            "canonicalCardId": f"card-{index:04d}",
            "cardName": f"Card {index}",
            "setId": "set-a",
            "setName": "Set A",
            "rarity": "Special Illustration Rare",
            "marketPrice": start - index,  # strictly positive across the whole range
        }
        for index in range(count)
    ]


def products(count):
    return [
        {
            "sealedProductId": f"product-{index:03d}",
            "productName": f"Product {index}",
            "setId": "set-a",
            "setName": "Set A",
            "productFamily": "elite_trainer_box",
            "productFamilyLabel": "Elite Trainer Box",
            "marketPrice": 100.0 - index,
        }
        for index in range(count)
    ]


def test_a_small_card_segment_publishes_a_complete_roster():
    summary = summarize_card_segment_constituents(cards(5), as_of="2026-08-25")
    assert summary["totalCount"] == 5
    assert summary["isComplete"] is True
    assert len(summary["topConstituents"]) == 5
    assert summary["asOf"] == "2026-08-25"
    assert summary["contractVersion"] == PREPARED_CONSTITUENT_SUMMARY_VERSION


def test_a_broad_card_segment_is_bounded_and_says_so():
    summary = summarize_card_segment_constituents(cards(4000), as_of="2026-08-25")
    assert summary["totalCount"] == 4000, "the true size is stated, never the preview length"
    assert len(summary["topConstituents"]) == DEFAULT_CARD_CONSTITUENT_LIMIT
    assert summary["isComplete"] is False
    assert summary["limit"] == DEFAULT_CARD_CONSTITUENT_LIMIT


def test_the_preview_is_the_most_valuable_constituents():
    summary = summarize_card_segment_constituents(cards(100), as_of="2026-08-25", limit=3)
    prices = [row["marketPrice"] for row in summary["topConstituents"]]
    assert prices == sorted(prices, reverse=True)
    assert prices[0] == 10000.0
    assert [row["rank"] for row in summary["topConstituents"]] == [1, 2, 3]


def test_ordering_is_reproducible_rather_than_row_order_dependent():
    rows = [
        {"canonicalCardId": "bbb", "marketPrice": 50.0},
        {"canonicalCardId": "aaa", "marketPrice": 50.0},
    ]
    forward = summarize_card_segment_constituents(rows, as_of="2026-08-25")
    backward = summarize_card_segment_constituents(list(reversed(rows)), as_of="2026-08-25")
    assert forward["topConstituents"] == backward["topConstituents"]
    assert forward["topConstituents"][0]["canonicalCardId"] == "aaa"


def test_asset_specific_fields_survive_verbatim():
    card = summarize_card_segment_constituents(cards(1), as_of="2026-08-25")["topConstituents"][0]
    assert card["rarity"] == "Special Illustration Rare"
    assert "productFamily" not in card, "no fake sealed field to force one row shape"

    product = summarize_sealed_segment_constituents(products(1), as_of="2026-08-25")["topConstituents"][0]
    assert product["productFamilyLabel"] == "Elite Trainer Box"
    assert product["setName"] == "Set A"
    assert "rarity" not in product


def test_the_id_field_is_declared_so_a_consumer_need_not_guess():
    assert summarize_card_segment_constituents(cards(1), as_of="x")["idField"] == "canonicalCardId"
    assert summarize_sealed_segment_constituents(products(1), as_of="x")["idField"] == "sealedProductId"


def test_no_historical_observation_leaks_into_the_summary():
    rows = [{
        "sealedProductId": "p1", "marketPrice": 100.0,
        "history": [{"date": "2026-01-01", "marketPrice": 50.0}],
    }]
    summary = summarize_sealed_segment_constituents(rows, as_of="2026-08-25")
    # The helper republishes the row it was given; the BUILDERS are responsible
    # for not handing it a history. This test pins that the builders do not.
    from backend.db.services.pokemon_global_sealed_market_service import _segment_series  # noqa: E402

    built = _segment_series(
        [{
            "sealedProductId": "p1", "name": "P1", "productFamily": "elite_trainer_box",
            "productFamilyLabel": "Elite Trainer Box", "setId": "set-a", "setName": "Set A",
            "currentPrice": 100.0,
            "history": [
                {"date": "2026-08-24", "marketPrice": 90.0},
                {"date": "2026-08-25", "marketPrice": 100.0},
            ],
        }],
        market_date="2026-08-25",
    )
    published = built["currentConstituents"]["topConstituents"][0]
    assert "history" not in published, "the current roster must not carry price history"
    assert published["marketPrice"] == pytest.approx(100.0)
    assert summary["topConstituents"][0]["marketPrice"] == pytest.approx(100.0)


def test_an_empty_segment_publishes_nothing_rather_than_an_empty_roster():
    assert summarize_card_segment_constituents([], as_of="2026-08-25") is None
    assert summarize_sealed_segment_constituents(
        [{"sealedProductId": "p", "marketPrice": 0}], as_of="2026-08-25",
    ) is None, "a non-positive price is not a constituent"


def test_a_sealed_family_roster_is_normally_complete():
    summary = summarize_sealed_segment_constituents(products(40), as_of="2026-08-25")
    assert summary["isComplete"] is True
    assert summary["totalCount"] == 40
