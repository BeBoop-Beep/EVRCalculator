import pytest

from backend.domain.pokemon.market_explorer_query import (
    MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION,
    MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION_V2,
    MarketExplorerQueryError, normalize_query_spec, query_fingerprint,
)


def normalize(instruments):
    return normalize_query_spec(mode="all", membership_mode="explicit", instruments=instruments)


def test_v2_qualified_identity_is_deduped_sorted_and_order_independent():
    left = normalize([{"asset": "sealed", "instrumentId": "b"}, {"asset": "cards", "instrumentId": "a"}, {"asset": "cards", "instrumentId": "a"}])
    right = normalize([{"asset": "cards", "instrumentId": "a"}, {"asset": "sealed", "instrumentId": "b"}])
    assert left["contractVersion"] == MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION_V2
    assert left["asset"] == "mixed"
    assert left["instruments"] == ({"asset": "cards", "instrumentId": "a"}, {"asset": "sealed", "instrumentId": "b"})
    assert query_fingerprint(left) == query_fingerprint(right)


def test_same_raw_id_in_different_assets_remains_distinct():
    spec = normalize([{"asset": "cards", "instrumentId": "same"}, {"asset": "sealed", "instrumentId": "same"}])
    assert len(spec["instruments"]) == 2


def test_v2_requires_one_to_twenty_five_leaves():
    with pytest.raises(MarketExplorerQueryError):
        normalize([])
    with pytest.raises(MarketExplorerQueryError):
        normalize([{"asset": "cards", "instrumentId": str(i)} for i in range(26)])
    assert len(normalize([{"asset": "cards", "instrumentId": str(i)} for i in range(25)])["instruments"]) == 25


def test_v1_identity_and_contract_remain_unchanged():
    spec = normalize_query_spec(mode="all", asset="cards", membership_mode="explicit", instrument_ids=["b", "a"])
    assert spec["contractVersion"] == MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION
    assert spec["instrumentIds"] == ("a", "b")
    assert "instruments" not in spec


def test_builder_axes_are_absent_from_new_exact_identity():
    spec = normalize_query_spec(mode="chase", membership_mode="explicit", instruments=[{"asset": "sealed", "instrumentId": "b"}], era_ids=["era"], set_ids=["set"], segment_ids=["ignored"], top_n=10)
    assert spec["eraIds"] == spec["setIds"] == spec["segmentIds"] == ()
    assert spec["mode"] == "all" and spec["topN"] is None

