import pytest

from backend.domain.access.index_plan_access import evaluate_market_query_access
from backend.domain.pokemon.market_explorer_query import (
    MarketExplorerQueryError, normalize_query_spec, query_fingerprint,
)


PINNED_FILTER_FINGERPRINTS = {
    "global_all_raw": ({"asset": "cards", "mode": "all"}, "66426743b657a45f4381f3a5b9a5f216158158d4dd3c6ba8b8da6ec56c53a8e6"),
    "global_top_10": ({"asset": "cards", "mode": "chase"}, "133fe00a0ad949916202f49d45e9cce6ba6daf6697c636f95ea714d1755bfe77"),
    "sir": ({"asset": "cards", "mode": "all", "segment_ids": ["specialIllustrationRare"]}, "3ddd972f0a97c650f5fb3578a2a1f9582da0b5031a8eed79917bfe7946980295"),
    "established": ({"asset": "cards", "mode": "all", "release_age_cohort_ids": ["established"]}, "d90b11c5a28e2ffd1e09e73f41d51eaeddd8d344fed44794cd61ed2d1d50fa85"),
    "era": ({"asset": "cards", "mode": "all", "era_ids": ["scarlet-violet"]}, "8f345b8a266757db56427248208620a471910993b201bbf27480069c722630cd"),
    "sealed": ({"asset": "sealed", "mode": "all"}, "2b3155dd63baf260bd17e0ec7c31ce886b9000721fb6fa86f771cb14892acc4c"),
}


@pytest.mark.parametrize("_name,pinned", PINNED_FILTER_FINGERPRINTS.items())
def test_v3_filter_fingerprints_remain_pinned(_name, pinned):
    kwargs, expected = pinned
    spec = normalize_query_spec(**kwargs)
    assert "membershipMode" not in spec and "instrumentIds" not in spec
    assert query_fingerprint(spec) == expected


def test_explicit_ids_are_required_bounded_sorted_and_deduplicated():
    with pytest.raises(MarketExplorerQueryError):
        normalize_query_spec(asset="cards", mode="all", membership_mode="explicit", instrument_ids=[])
    with pytest.raises(MarketExplorerQueryError):
        normalize_query_spec(asset="cards", mode="all", membership_mode="explicit", instrument_ids=range(1, 27))
    left = normalize_query_spec(asset="cards", mode="all", membership_mode="explicit",
                                instrument_ids=["b", "a", "b", " "])
    right = normalize_query_spec(asset="cards", mode="all", membership_mode="explicit",
                                 instrument_ids=["a", "b"])
    assert left["instrumentIds"] == ("a", "b")
    assert query_fingerprint(left) == query_fingerprint(right)
    assert left["contractVersion"] != "pokemon-market-explorer-query-v3-variant"


def test_explicit_membership_is_a_premium_axis():
    spec = normalize_query_spec(asset="sealed", mode="all", membership_mode="explicit",
                                instrument_ids=["00000000-0000-0000-0000-000000000001"])
    assert evaluate_market_query_access("plus", spec)["allowed"] is False
    assert evaluate_market_query_access("premium", spec)["allowed"] is True


def test_filtered_ids_have_no_identity_effect_and_explicit_filters_are_canonicalized_away():
    filtered = normalize_query_spec(asset="cards", mode="all", membership_mode="filters",
                                    instrument_ids=["stale"], segment_ids=["specialIllustrationRare"],
                                    price_segment_ids=["intermediate"], release_age_cohort_ids=["new"])
    clean = normalize_query_spec(asset="cards", mode="all", segment_ids=["specialIllustrationRare"],
                                 price_segment_ids=["intermediate"], release_age_cohort_ids=["new"])
    assert filtered == clean
    assert query_fingerprint(filtered) == query_fingerprint(clean)

    exact = normalize_query_spec(asset="cards", mode="chase", membership_mode="explicit",
                                 instrument_ids=["variant-a"], era_ids=["sv"],
                                 segment_ids=["specialIllustrationRare"],
                                 price_segment_ids=["intermediate"], release_age_cohort_ids=["new"], top_n=10)
    assert exact["instrumentIds"] == ("variant-a",)
    assert exact["eraIds"] == exact["segmentIds"] == exact["priceSegmentIds"] == exact["releaseAgeCohortIds"] == ()
    assert exact["mode"] == "all" and exact["topN"] is None
    assert query_fingerprint(exact) != query_fingerprint(clean)
