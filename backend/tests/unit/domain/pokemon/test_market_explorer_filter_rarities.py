from backend.domain.pokemon.card_rarity_taxonomy import (
    FILTER_RARITY_DEFINITIONS, RAW_CARD_SEGMENT_DEFINITIONS, normalize_filter_rarity,
)
from backend.domain.pokemon.market_explorer_query import normalize_query_spec


def test_full_filter_taxonomy_is_distinct_from_nine_prepared_markets():
    filter_ids = {row["key"] for row in FILTER_RARITY_DEFINITIONS}
    prepared_ids = {row["key"] for row in RAW_CARD_SEGMENT_DEFINITIONS}
    assert len(filter_ids) == 39
    assert len(prepared_ids) == 9
    assert prepared_ids < filter_ids
    assert {"legend", "radiantRare", "aceSpecRare"} <= filter_ids - prepared_ids


def test_filter_normalization_is_exact_and_preserves_distinct_rarities():
    assert normalize_filter_rarity("RARE-HOLO-V") == "rareHoloV"
    assert normalize_filter_rarity("Rare Holo LV.X") == "rareHoloLvX"
    assert normalize_filter_rarity("Rare Ultra") == "rareUltra"
    assert normalize_filter_rarity("Ultra Rare") == "ultraRare"
    assert normalize_filter_rarity("Rare Holo-ish") is None


def test_filter_only_rarity_combines_with_price_and_age_in_query_contract():
    spec = normalize_query_spec(asset="cards", mode="all", segment_ids=["legend", "radiantRare"],
                                price_segment_ids=["obtainable"], release_age_cohort_ids=["legacy"])
    assert spec["segmentIds"] == ("legend", "radiantRare")
    assert spec["priceSegmentIds"] == ("obtainable",)
    assert spec["releaseAgeCohortIds"] == ("legacy",)
