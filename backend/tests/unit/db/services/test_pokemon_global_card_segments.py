"""Raw Card Market rarity submarkets.

Every assertion guards one of the ways a rarity index could lie: splitting one
rarity across two markets on a spelling difference, folding a distinct rarity
into a neighbouring one by substring, letting a card entering the universe
manufacture a return, publishing an index over a handful of cards, or breaking
reconciliation with the parent Raw Card Market.
"""

from __future__ import annotations

import json

import pytest

from backend.db.services.pokemon_global_card_market_segments_service import (
    CARD_SEGMENT_CONTRACT_VERSION,
    TOP_CHASE_SEGMENTS_UNAVAILABLE_REASON,
    build_card_segments_payload,
    build_global_card_segments,
    partition_constituent_rows,
)
from backend.db.services.pokemon_market_index_service import build_market_overview
from backend.domain.pokemon.card_rarity_taxonomy import (
    CARD_RARITY_TAXONOMY_VERSION,
    MIN_SEGMENT_CARD_COUNT,
    MIN_SEGMENT_SET_COUNT,
    RAW_CARD_SEGMENT_DEFINITIONS,
    RESIDUAL_CARD_SEGMENT_KEY,
    meets_quality_gate,
    normalize_rarity,
    partition_cards_by_segment,
    segment_key_for_rarity,
    taxonomy_metadata,
)

DAYS = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]


def rows(card_id, prices, *, start=0):
    return [
        {"canonical_card_id": card_id, "market_date": DAYS[start + offset], "market_price": price}
        for offset, price in enumerate(prices)
    ]


def card(card_id, set_id, rarity):
    return {"canonicalCardId": card_id, "setId": set_id, "name": card_id, "rawRarity": rarity,
            "rarityKey": normalize_rarity(rarity)}


# A universe with enough cards and sets that SIR clears the gate, IR clears it,
# and Ultra Rare deliberately does not (only two cards from two sets).
def universe():
    rarity_by_card: dict[str, dict] = {}
    constituent_rows: list[dict] = []

    def add(card_id, set_id, rarity, prices, *, start=0):
        rarity_by_card[card_id] = card(card_id, set_id, rarity)
        constituent_rows.extend(rows(card_id, prices, start=start))

    # 26 SIRs across 3 sets, all doubling then holding: index 100 -> 200.
    for index in range(26):
        add(f"sir-{index}", f"set-{index % 3}", "Special Illustration Rare", [10.0, 20.0, 20.0, 20.0])
    # 30 IRs across 5 sets, halving: index 100 -> 50. Deliberately opposite, so
    # a segment reading another segment's data fails loudly.
    for index in range(30):
        # Mixed spellings of the SAME rarity, which must NOT split the market.
        rarity = "Illustration Rare" if index % 2 else "illustration rare"
        add(f"ir-{index}", f"set-{index % 5}", rarity, [40.0, 20.0, 20.0, 20.0])
    # Two Ultra Rares from two sets: below both gate dimensions.
    add("ur-0", "set-0", "Ultra Rare", [5.0, 5.0, 5.0, 5.0])
    add("ur-1", "set-1", "ultra rare", [5.0, 5.0, 5.0, 5.0])
    # Residual: base rarities and a distinct rarity that must not be folded in.
    add("common-0", "set-0", "Common", [1.0, 1.0, 1.0, 1.0])
    add("mega-0", "set-0", "Mega Hyper Rare", [100.0, 100.0, 100.0, 100.0])
    add("shiny-0", "set-0", "Shiny Ultra Rare", [50.0, 50.0, 50.0, 50.0])
    return constituent_rows, rarity_by_card


def build(constituent_rows=None, rarity_by_card=None, *, market_date="2026-01-04", parent=None):
    if constituent_rows is None:
        constituent_rows, rarity_by_card = universe()
    return build_global_card_segments(
        constituent_rows, rarity_by_card, market_date=market_date, parent_basket_value=parent,
    )


# --- taxonomy / normalization (spec 4, 36) --------------------------------

def test_the_same_rarity_under_different_spellings_is_one_market():
    for spelling in ("Illustration Rare", "illustration rare", "ILLUSTRATION RARE",
                     "  Illustration   Rare  ", "illustration-rare", "ILLUSTRATION_RARE"):
        assert normalize_rarity(spelling) == "illustrationRare", spelling
    for spelling in ("Double Rare", "double rare", "DOUBLE_RARE"):
        assert normalize_rarity(spelling) == "doubleRare", spelling


def test_normalization_is_exact_match_and_never_a_substring_test():
    # These read like modifiers of a published rarity and must stay distinct;
    # a substring test would silently fold each into the segment beside it.
    assert normalize_rarity("Mega Hyper Rare") == "megaHyperRare"
    assert normalize_rarity("Hyper Rare") == "hyperRare"
    assert normalize_rarity("Shiny Ultra Rare") == "shinyUltraRare"
    assert normalize_rarity("Ultra Rare") == "ultraRare"
    assert normalize_rarity("Special Illustration Rare") == "specialIllustrationRare"
    assert normalize_rarity("Illustration Rare") == "illustrationRare"
    # And each maps to a DIFFERENT published segment (or to none at all).
    assert segment_key_for_rarity("Mega Hyper Rare") is None
    assert segment_key_for_rarity("Hyper Rare") == "hyperRare"
    assert segment_key_for_rarity("Shiny Ultra Rare") is None
    assert segment_key_for_rarity("Ultra Rare") == "ultraRare"


def test_an_unrecognised_rarity_lands_in_the_residual_rather_than_a_neighbour():
    assert normalize_rarity("Radiant Rare") is None
    assert normalize_rarity("Radiant Rare") is None
    assert normalize_rarity("") is None
    assert normalize_rarity(None) is None
    assert segment_key_for_rarity("Radiant Rare") is None


def test_a_card_belongs_to_exactly_one_published_segment():
    seen: dict[str, str] = {}
    for definition in RAW_CARD_SEGMENT_DEFINITIONS:
        for rarity_key in definition["rarityKeys"]:
            assert rarity_key not in seen, f"{rarity_key} claimed by two segments"
            seen[rarity_key] = str(definition["key"])
    grouped = partition_cards_by_segment([
        {"rarity": "Special Illustration Rare"}, {"rarity": "illustration rare"},
        {"rarity": "Radiant Rare"},
    ])
    assert len(grouped["specialIllustrationRare"]) == 1
    assert len(grouped["illustrationRare"]) == 1
    assert len(grouped[RESIDUAL_CARD_SEGMENT_KEY]) == 1
    assert sum(len(value) for value in grouped.values()) == 3


def test_the_taxonomy_publishes_a_version_so_a_correction_is_auditable():
    metadata = taxonomy_metadata()
    assert metadata["taxonomyVersion"] == CARD_RARITY_TAXONOMY_VERSION
    assert metadata["parentMarket"] == "raw"
    assert metadata["disjoint"] is True
    assert [entry["key"] for entry in metadata["segments"]] == [
        "specialIllustrationRare", "illustrationRare", "ultraRare", "hyperRare", "doubleRare",
        "rareUltra", "rareSecret", "rareRainbow", "rareHolo",
    ]
    assert all(entry["definition"] for entry in metadata["segments"])
    # The definitions explain MEMBERSHIP, never whether a segment is a good buy.
    joined = " ".join(entry["definition"] for entry in metadata["segments"]).lower()
    for forbidden in ("buy", "sell", "invest", "undervalued", "opportunity"):
        assert forbidden not in joined


# --- quality gate (spec 7) ------------------------------------------------

def test_the_quality_gate_needs_both_enough_cards_and_enough_sets():
    assert meets_quality_gate(card_count=MIN_SEGMENT_CARD_COUNT, set_count=MIN_SEGMENT_SET_COUNT)
    assert not meets_quality_gate(card_count=MIN_SEGMENT_CARD_COUNT - 1, set_count=22)
    # 120 cards that all live in ONE set is that set's mechanic, not a market.
    assert not meets_quality_gate(card_count=120, set_count=1)
    assert not meets_quality_gate(card_count=2, set_count=2)


def test_a_segment_below_the_gate_is_published_unavailable_with_a_reason():
    published = build()
    ultra = published["segments"]["ultraRare"]
    assert ultra["available"] is False
    assert "quality gate" in ultra["unavailableReason"]
    # It still reports what it measured, so the gate decision is auditable.
    assert ultra["metadata"]["cardCount"] == 2
    assert "indexValue" not in ultra


def test_a_rarity_with_no_constituents_is_published_unavailable_not_as_a_zero():
    published = build()
    hyper = published["segments"]["hyperRare"]
    assert hyper["available"] is False
    assert hyper["unavailableReason"] == "no eligible constituent history"
    assert "basketValue" not in hyper


# --- membership (spec 36) -------------------------------------------------

def test_only_matching_cards_enter_a_rarity_segment():
    constituent_rows, rarity_by_card = universe()
    grouped = partition_constituent_rows(constituent_rows, rarity_by_card)
    sir_cards = {row["canonical_card_id"] for row in grouped["specialIllustrationRare"]}
    ir_cards = {row["canonical_card_id"] for row in grouped["illustrationRare"]}
    assert all(card_id.startswith("sir-") for card_id in sir_cards)
    assert all(card_id.startswith("ir-") for card_id in ir_cards)
    assert sir_cards & ir_cards == set()
    # Mega Hyper Rare and Shiny Ultra Rare went to the residual, not to their
    # look-alike segments.
    residual = {row["canonical_card_id"] for row in grouped[RESIDUAL_CARD_SEGMENT_KEY]}
    assert {"mega-0", "shiny-0", "common-0"} <= residual
    assert sum(len(value) for value in grouped.values()) == len(constituent_rows)


def test_both_spellings_of_one_rarity_land_in_the_same_segment():
    published = build()
    illustration = published["segments"]["illustrationRare"]
    # All 30 IRs, regardless of spelling.
    assert illustration["metadata"]["cardCount"] == 30
    assert illustration["metadata"]["setCount"] == 5


# --- index behaviour (spec 37, 38) ----------------------------------------

def test_common_cohort_price_movement_moves_the_index_correctly():
    published = build()
    sir = published["segments"]["specialIllustrationRare"]
    # 26 cards at $10 -> $20 is exactly +100%.
    assert sir["indexValue"] == pytest.approx(200.0)
    assert sir["familyChanges"]["SinceTracking"]["percent"] == pytest.approx(100.0)
    assert sir["basketValue"] == pytest.approx(520.0)

    illustration = published["segments"]["illustrationRare"]
    # 30 cards at $40 -> $20 is exactly -50%. A segment reading another
    # segment's constituents could not produce opposite directions.
    assert illustration["indexValue"] == pytest.approx(50.0)
    assert illustration["familyChanges"]["SinceTracking"]["percent"] == pytest.approx(-50.0)


def test_a_card_entering_moves_tracked_value_but_not_the_index():
    constituent_rows, rarity_by_card = universe()
    # A 27th SIR appears on day 3 at $500.
    rarity_by_card["sir-new"] = card("sir-new", "set-0", "Special Illustration Rare")
    constituent_rows.extend(rows("sir-new", [500.0, 500.0], start=2))
    published = build(constituent_rows, rarity_by_card)
    sir = published["segments"]["specialIllustrationRare"]

    tracked = {point["date"]: point["value"] for point in sir["trackedValueHistory"]}
    assert tracked["2026-01-02"] == pytest.approx(520.0)
    assert tracked["2026-01-03"] == pytest.approx(1020.0)  # 520 + 500
    # The index still reports only the common cohort's real move, so the $500
    # arrival adds nothing to price performance on the day it enters.
    index_by_date = {point[0]: point[1] for point in sir["trend"]}
    assert index_by_date["2026-01-02"] == pytest.approx(200.0)
    assert index_by_date["2026-01-03"] == pytest.approx(200.0)
    assert sir["indexValue"] == pytest.approx(200.0)


def test_a_card_leaving_does_not_fabricate_a_decline():
    constituent_rows, rarity_by_card = universe()
    # One SIR stops reporting after day 2 while every other price holds.
    constituent_rows = [
        row for row in constituent_rows
        if not (row["canonical_card_id"] == "sir-0" and row["market_date"] > "2026-01-02")
    ]
    published = build(constituent_rows, rarity_by_card)
    sir = published["segments"]["specialIllustrationRare"]
    index_by_date = {point[0]: point[1] for point in sir["trend"]}
    assert index_by_date["2026-01-03"] == pytest.approx(200.0)
    assert index_by_date["2026-01-04"] == pytest.approx(200.0)
    # Tracked Value legitimately drops by the departed card.
    tracked = {point["date"]: point["value"] for point in sir["trackedValueHistory"]}
    assert tracked["2026-01-03"] == pytest.approx(500.0)


def test_segments_are_built_from_their_own_cards_not_sliced_from_a_finished_index():
    published = build()
    # The two large segments move in opposite directions on the same days. No
    # decomposition of one parent index can produce that.
    assert published["segments"]["specialIllustrationRare"]["indexValue"] > 100.0
    assert published["segments"]["illustrationRare"]["indexValue"] < 100.0


# --- reconciliation (spec 34, 40) -----------------------------------------

def test_published_segments_plus_residual_reconcile_to_the_parent():
    constituent_rows, rarity_by_card = universe()
    parent_value = sum(
        float(row["market_price"]) for row in constituent_rows if row["market_date"] == "2026-01-04"
    )
    published = build(constituent_rows, rarity_by_card, parent=parent_value)
    reconciliation = published["reconciliation"]
    total = reconciliation["publishedSegmentBasketValue"] + reconciliation["residual"]["basketValue"]
    assert total == pytest.approx(parent_value, abs=0.02)
    assert reconciliation["parentBasketValue"] == pytest.approx(parent_value)
    assert reconciliation["parentMarket"] == "raw"


def test_a_gated_segment_s_cards_fall_into_the_residual_rather_than_vanishing():
    constituent_rows, rarity_by_card = universe()
    parent_value = sum(
        float(row["market_price"]) for row in constituent_rows if row["market_date"] == "2026-01-04"
    )
    published = build(constituent_rows, rarity_by_card, parent=parent_value)
    residual = published["reconciliation"]["residual"]
    # Ultra Rare ($10) failed the gate, so its dollars are in the residual with
    # Common ($1), Mega Hyper Rare ($100) and Shiny Ultra Rare ($50).
    assert residual["basketValue"] == pytest.approx(161.0)
    assert residual["label"] == "Other Cards"


# --- Top Chase (spec 18) ---------------------------------------------------

def test_top_chase_rarity_segments_are_published_unavailable_with_the_missing_authority():
    payload = build_card_segments_payload(build())
    chase = payload["topChase"]
    assert chase["available"] is False
    assert chase["segments"] == {}
    assert "membership" in chase["unavailableReason"]
    assert "value_scope='top10'" in chase["unavailableReason"]
    assert chase["unavailableReason"] == TOP_CHASE_SEGMENTS_UNAVAILABLE_REASON


def test_the_payload_degrades_when_no_card_history_is_available():
    payload = build_card_segments_payload(None)
    assert payload["raw"]["available"] is False
    assert payload["raw"]["segments"] == {}
    assert payload["contractVersion"] == CARD_SEGMENT_CONTRACT_VERSION


# --- serialization / contract (spec 20) -----------------------------------

def test_every_available_segment_carries_the_required_contract_fields():
    published = build()
    json.dumps(published)  # must not raise
    for key in ("specialIllustrationRare", "illustrationRare"):
        segment = published["segments"][key]
        for field in ("key", "label", "parentMarket", "available", "basketValue", "indexValue",
                      "historyStartDate", "familyChanges", "basketChanges", "trend",
                      "trackedValueHistory", "metadata", "definition", "taxonomyVersion"):
            assert field in segment, f"{key} is missing {field}"
        assert segment["parentMarket"] == "raw"
        assert segment["taxonomyVersion"] == CARD_RARITY_TAXONOMY_VERSION
        assert segment["metadata"]["cardCount"] > 0
        assert segment["metadata"]["setCount"] > 0
    # No raw observation rows leak into the public payload.
    serialized = json.dumps(published)
    assert "canonical_card_id" not in serialized
    assert "market_price" not in serialized


def test_the_index_level_and_own_since_tracking_reconcile():
    published = build()
    for key in ("specialIllustrationRare", "illustrationRare"):
        segment = published["segments"][key]
        percent = segment["familyChanges"]["SinceTracking"]["percent"]
        # base 100: an index of 200 is +100%, an index of 50 is -50%.
        assert segment["indexValue"] == pytest.approx(100.0 * (1.0 + percent / 100.0))


# --- parent regression (spec 13, 23, 41) ----------------------------------

FINGERPRINT = "cohort"


def index_row(index_key, day, value, basket):
    return {"index_key": index_key, "market_date": day, "normalized_index_value": value,
            "basket_value": basket, "set_count": 3,
            "card_count": 30 if index_key == "raw" else 30,
            "cohort_fingerprint": FINGERPRINT,
            "source_generation_fingerprint": f"{index_key}-{day}"}


HISTORY = (
    [index_row("raw", day, value, 8000.0) for day, value in
     (("2026-01-01", 100.0), ("2026-01-02", 102.0), ("2026-01-03", 104.0), ("2026-01-04", 106.0))]
    + [index_row("top10", day, value, 4000.0) for day, value in
       (("2026-01-01", 100.0), ("2026-01-02", 99.0), ("2026-01-03", 98.0), ("2026-01-04", 97.0))]
)


def test_attaching_card_segments_leaves_every_parent_number_identical():
    without = build_market_overview(HISTORY, market_date="2026-01-04")
    payload = build_card_segments_payload(build())
    with_segments = build_market_overview(HISTORY, market_date="2026-01-04", card_segments=payload)
    for key in ("raw", "topChase"):
        for field in ("basketValue", "indexValue", "changes", "familyChanges", "trend"):
            assert with_segments[key][field] == without[key][field], f"{key}.{field}"
    assert with_segments["comparisonWindows"] == without["comparisonWindows"]


def test_each_card_segment_is_measured_against_the_parents_shared_domain():
    payload = build_card_segments_payload(build())
    overview = build_market_overview(HISTORY, market_date="2026-01-04", card_segments=payload)
    sir = overview["cardSegments"]["raw"]["segments"]["specialIllustrationRare"]
    # Its own history is preserved...
    assert sir["familyChanges"]["SinceTracking"]["percent"] == pytest.approx(100.0)
    # ...and it also carries a shared-comparison series so it is comparable
    # against Raw and Top Chase on the same chart.
    assert "changes" in sir


def test_the_overview_omits_card_segments_entirely_when_none_are_supplied():
    assert "cardSegments" not in build_market_overview(HISTORY, market_date="2026-01-04")


def test_the_catalogue_read_emits_the_keys_the_constituent_summary_consumes():
    """Both naming conventions, or prepared card constituents publish nulls.

    `read_canonical_card_rarities` keys the partitioning on `rawRarity`, while
    the published `currentConstituents` rows read `cardName`, `cardNumber`,
    `rarity`, `imageUrl` and `setName`. Only the first set existed, so every
    prepared card segment built 25 rows carrying an id, a price and nothing a
    reader could recognise. This pins both halves.
    """
    from backend.db.services.pokemon_global_card_market_segments_service import (
        read_canonical_card_rarities,
    )

    class Result:
        def __init__(self, data):
            self.data = data

    class Query:
        def __init__(self, rows):
            self._rows = rows

        def select(self, *_a, **_k):
            return self

        def in_(self, *_a, **_k):
            return self

        def order(self, *_a, **_k):
            return self

        def range(self, start, end):
            self._range = (start, end)
            return self

        def execute(self):
            start, end = getattr(self, "_range", (0, 999))
            return Result(self._rows[start:end + 1])

    class Client:
        def table(self, name):
            if name == "sets":
                return Query([{"id": "set-a", "name": "Ascended Heroes"}])
            return Query([{
                "id": "card-1", "set_id": "set-a", "name": "Umbreon ex",
                "number": "161", "rarity": "Special Illustration Rare",
                "image_small_url": "http://img/161.png",
            }])

    card = read_canonical_card_rarities(Client(), ["set-a"])["card-1"]

    # What the published summary reads.
    assert card["cardName"] == "Umbreon ex"
    assert card["cardNumber"] == "161"
    assert card["rarity"] == "Special Illustration Rare"
    assert card["imageUrl"] == "http://img/161.png"
    assert card["setName"] == "Ascended Heroes"
    # What the segment partitioning reads — unchanged.
    assert card["rawRarity"] == "Special Illustration Rare"
    assert card["rarityKey"] == "specialIllustrationRare"
    assert card["setId"] == "set-a"
