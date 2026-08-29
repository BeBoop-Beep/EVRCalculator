"""Filter-first Market Explorer query model.

Every test here encodes a rule from the Phase-3 specification, and the
NEGATIVE ones matter most: the rejected Phase-3 direction (per-set quotas,
today's Top 10 projected backward) would still pass a naive "the Top 10 has
ten cards" assertion. These assert the properties that separate the two
models.
"""

from __future__ import annotations

import pytest

from backend.domain.pokemon.market_explorer_query import (
    DEFAULT_CHASE_TOP_N,
    MODE_ALL,
    MODE_CHASE,
    MarketExplorerQueryError,
    build_chain_linked_history_from_cohorts,
    build_query_observations,
    filter_point_in_time_rows,
    active_filter_axes,
    normalize_query_spec,
    query_fingerprint,
    query_key,
    rank_chase_constituents,
    price_segment_for,
    release_age_cohort_for,
)


def test_pass3_axes_normalize_deduplicate_and_fingerprint_deterministically():
    a = normalize_query_spec(mode=MODE_ALL, pokemon_ids=["149", "149"], price_segment_ids=["premium"], release_age_cohort_ids=["new"])
    b = normalize_query_spec(mode=MODE_ALL, pokemon_ids=["149"], price_segment_ids=["premium"], release_age_cohort_ids=["new"])
    assert a["pokemonIds"] == ("149",)
    assert active_filter_axes(a) == ("pokemon", "priceSegment", "releaseAge")
    assert query_fingerprint(a) == query_fingerprint(b)


@pytest.mark.parametrize("field,value", [("price_segment_ids", ["luxury"]), ("release_age_cohort_ids", ["ancient"])])
def test_unknown_pass3_taxonomy_ids_fail(field, value):
    with pytest.raises(MarketExplorerQueryError):
        normalize_query_spec(mode=MODE_ALL, **{field: value})


def test_sealed_rejects_pokemon_axis():
    with pytest.raises(MarketExplorerQueryError):
        normalize_query_spec(mode=MODE_ALL, asset="sealed", pokemon_ids=["149"])


def test_price_segment_membership_is_point_in_time_and_precedes_ranking():
    rows = [
        {"marketDate": "2026-01-01", "canonicalCardId": "dragonite", "marketPrice": 9},
        {"marketDate": "2026-04-01", "canonicalCardId": "dragonite", "marketPrice": 50},
        {"marketDate": "2026-08-01", "canonicalCardId": "dragonite", "marketPrice": 150},
    ]
    assert [row["marketDate"] for row in filter_point_in_time_rows(rows, asset="cards", price_segment_ids=["obtainable"])] == ["2026-01-01"]
    assert [row["marketDate"] for row in filter_point_in_time_rows(rows, asset="cards", price_segment_ids=["intermediate"])] == ["2026-04-01"]
    assert [row["marketDate"] for row in filter_point_in_time_rows(rows, asset="cards", price_segment_ids=["premium"])] == ["2026-08-01"]
    assert price_segment_for("sealed", 499.99) == "intermediate"


def test_release_age_membership_transitions_by_observation_date():
    assert release_age_cohort_for("2025-01-01", "2025-03-01") == "new"
    assert release_age_cohort_for("2025-01-01", "2026-01-02") == "recent"
    assert release_age_cohort_for("2025-01-01", "2028-01-02") == "established"
    assert release_age_cohort_for("2025-01-01", "2031-01-02") == "legacy"


def _c(card_id: str, price: float) -> dict:
    return {"canonicalCardId": card_id, "marketPrice": price}


# ---------------------------------------------------------------------------
# Normalization / identity (spec sections 6-8)
# ---------------------------------------------------------------------------

def test_empty_scope_means_all_and_normalizes_to_empty_tuples():
    spec = normalize_query_spec(mode=MODE_ALL)
    assert spec["eraIds"] == () and spec["setIds"] == () and spec["segmentIds"] == ()
    assert spec["mode"] == MODE_ALL
    # topN is meaningless outside chase and must not be carried.
    assert spec["topN"] is None


def test_chase_defaults_to_top_10():
    assert normalize_query_spec(mode=MODE_CHASE)["topN"] == DEFAULT_CHASE_TOP_N


def test_multi_select_ids_are_sorted_and_deduplicated():
    spec = normalize_query_spec(
        mode=MODE_ALL,
        era_ids=["b", "a", "b"],
        segment_ids=["ultraRare", "illustrationRare", "ultraRare"],
    )
    assert spec["eraIds"] == ("a", "b")
    assert spec["segmentIds"] == ("illustrationRare", "ultraRare")


def test_era_and_set_are_one_logical_scope_axis():
    spec = normalize_query_spec(mode=MODE_ALL, era_ids=["sv"], set_ids=["tef"])
    assert active_filter_axes(spec) == ("scope",)


def test_scope_and_segment_are_two_independent_axes():
    spec = normalize_query_spec(mode=MODE_ALL, set_ids=["tef"], segment_ids=["specialIllustrationRare"])
    assert active_filter_axes(spec) == ("scope", "segment")


def test_equivalent_selections_share_one_fingerprint():
    a = normalize_query_spec(mode=MODE_CHASE, era_ids=["sv", "swsh"], segment_ids=["specialIllustrationRare"])
    b = normalize_query_spec(mode=MODE_CHASE, era_ids=["swsh", "sv"], segment_ids=["specialIllustrationRare"])
    assert query_fingerprint(a) == query_fingerprint(b)
    assert query_key(a) == query_key(b)


def test_differing_selections_do_not_collide():
    a = normalize_query_spec(mode=MODE_CHASE, segment_ids=["specialIllustrationRare"])
    b = normalize_query_spec(mode=MODE_ALL, segment_ids=["specialIllustrationRare"])
    assert query_fingerprint(a) != query_fingerprint(b)


def test_query_key_is_human_readable_and_stable():
    spec = normalize_query_spec(mode=MODE_CHASE, segment_ids=["specialIllustrationRare"])
    assert query_key(spec) == (
        "cards|era=all|set=all|segment=specialIllustrationRare|pokemon=all|priceSegment=all|releaseAge=all|mode=chase|topN=10"
    )


def test_invalid_mode_is_rejected():
    with pytest.raises(MarketExplorerQueryError):
        normalize_query_spec(mode="topten")


def test_non_positive_top_n_is_rejected():
    with pytest.raises(MarketExplorerQueryError):
        normalize_query_spec(mode=MODE_CHASE, top_n=0)


# ---------------------------------------------------------------------------
# Chase ranking (spec sections 16, 40-42)
# ---------------------------------------------------------------------------

def test_no_set_quota_one_set_may_occupy_most_of_the_basket():
    """Spec section 40. Set A holds 5 of the 10 highest prices; all 5 survive."""
    universe = [_c(f"a{i}", 1000 - i) for i in range(5)] + [_c(f"b{i}", 500 - i) for i in range(10)]
    picked = rank_chase_constituents(universe, 10)
    assert sum(1 for row in picked if row["canonicalCardId"].startswith("a")) == 5


def test_zero_representation_for_a_set_below_the_cutoff():
    """Spec section 41. Set B is cheap everywhere and contributes nothing."""
    universe = [_c(f"a{i}", 1000 - i) for i in range(10)] + [_c(f"b{i}", 1.0) for i in range(10)]
    picked = rank_chase_constituents(universe, 10)
    assert all(row["canonicalCardId"].startswith("a") for row in picked)


def test_fewer_than_top_n_returns_what_exists_without_filler():
    """Spec section 42."""
    picked = rank_chase_constituents([_c(f"a{i}", 100 - i) for i in range(6)], 10)
    assert len(picked) == 6


def test_ties_break_on_canonical_card_id_not_input_order():
    shuffled = [_c("zzz", 50.0), _c("aaa", 50.0), _c("mmm", 50.0)]
    assert [row["canonicalCardId"] for row in rank_chase_constituents(shuffled, 2)] == ["aaa", "mmm"]


def test_ranking_is_by_price_descending():
    picked = rank_chase_constituents([_c("a", 1.0), _c("b", 99.0), _c("c", 50.0)], 3)
    assert [row["canonicalCardId"] for row in picked] == ["b", "c", "a"]


# ---------------------------------------------------------------------------
# Daily membership (spec sections 14, 15, 43)
# ---------------------------------------------------------------------------

def test_membership_is_recomputed_per_date_and_never_backfilled():
    """Spec sections 14/15/43. Card B overtakes Card A on day 2.

    The rejected model would put today's winner (B) into day 1 as well. Day 1
    must still contain A and must NOT contain B.
    """
    rows = [
        {"marketDate": "2026-01-01", "canonicalCardId": "A", "marketPrice": 100.0},
        {"marketDate": "2026-01-01", "canonicalCardId": "B", "marketPrice": 10.0},
        {"marketDate": "2026-01-02", "canonicalCardId": "A", "marketPrice": 100.0},
        {"marketDate": "2026-01-02", "canonicalCardId": "B", "marketPrice": 900.0},
    ]
    observations = build_query_observations(rows, mode=MODE_CHASE, top_n=1)
    day1, day2 = observations
    assert [row["setId"] for row in day1["constituents"]] == ["A"]
    assert [row["setId"] for row in day2["constituents"]] == ["B"]


def test_all_mode_retains_every_eligible_constituent():
    rows = [
        {"marketDate": "2026-01-01", "canonicalCardId": "A", "marketPrice": 100.0},
        {"marketDate": "2026-01-01", "canonicalCardId": "B", "marketPrice": 10.0},
    ]
    observations = build_query_observations(rows, mode=MODE_ALL, top_n=None)
    assert len(observations[0]["constituents"]) == 2


def test_non_positive_prices_are_dropped_not_zero_filled():
    rows = [
        {"marketDate": "2026-01-01", "canonicalCardId": "A", "marketPrice": 100.0},
        {"marketDate": "2026-01-01", "canonicalCardId": "B", "marketPrice": 0.0},
        {"marketDate": "2026-01-01", "canonicalCardId": "C", "marketPrice": None},
    ]
    observations = build_query_observations(rows, mode=MODE_ALL, top_n=None)
    assert [row["setId"] for row in observations[0]["constituents"]] == ["A"]


def test_observations_carry_requested_and_actual_counts():
    rows = [{"marketDate": "2026-01-01", "canonicalCardId": "A", "marketPrice": 5.0}]
    day = build_query_observations(rows, mode=MODE_CHASE, top_n=10)[0]
    assert day["requestedTopN"] == 10
    assert day["actualConstituentCount"] == 1


# ---------------------------------------------------------------------------
# Fast-path parity (cohort-aggregate chain-link vs row-based chain-link)
# ---------------------------------------------------------------------------

def _cohorts_from_rows(rows, *, mode, top_n):
    """Compute what the SQL cohort RPC would return, from raw card-date rows.

    This mirrors the RPC's aggregation in Python so the two chain-linkers can be
    compared on identical input without a database.
    """
    observations = build_query_observations(rows, mode=mode, top_n=top_n)
    cohorts = []
    previous = None
    for observation in observations:
        current = {row["setId"]: float(row["setValue"]) for row in observation["constituents"]}
        if previous is None:
            common_ids = set()
        else:
            common_ids = previous.keys() & current.keys()
        cohorts.append({
            "marketDate": observation["marketDate"],
            "constituentCount": observation["actualConstituentCount"],
            "eligibleUniverseCount": observation["eligibleUniverseCount"],
            "basketValue": round(sum(current.values()), 2),
            "commonCount": len(common_ids),
            "commonCurrentValue": round(sum(current[key] for key in common_ids), 2),
            "commonPreviousValue": round(sum(previous[key] for key in common_ids), 2) if previous else 0.0,
        })
        previous = current
    return cohorts


def _row(date_, card, price):
    return {"marketDate": date_, "canonicalCardId": card, "marketPrice": price}


def test_cohort_chain_link_matches_the_row_based_chain_link():
    """The fast path must not be a second, subtly different index."""
    from backend.domain.pokemon.market_index import build_chain_linked_history_with_segments

    rows = [
        _row("2026-01-01", "A", 100.0), _row("2026-01-01", "B", 50.0),
        _row("2026-01-02", "A", 110.0), _row("2026-01-02", "B", 55.0),
        # C enters and B leaves -- a roster change mid-series.
        _row("2026-01-03", "A", 121.0), _row("2026-01-03", "C", 900.0),
        _row("2026-01-04", "A", 121.0), _row("2026-01-04", "C", 990.0),
    ]
    observations = build_query_observations(rows, mode=MODE_ALL, top_n=None)
    row_based = build_chain_linked_history_with_segments(observations)
    cohort_based = build_chain_linked_history_from_cohorts(
        _cohorts_from_rows(rows, mode=MODE_ALL, top_n=None)
    )

    assert len(row_based) == len(cohort_based)
    for expected, actual in zip(row_based, cohort_based):
        assert expected["marketDate"] == actual["marketDate"]
        assert actual["normalizedIndexValue"] == pytest.approx(expected["normalizedIndexValue"])
        assert actual["basketValue"] == pytest.approx(expected["basketValue"])
        assert actual["chainSegmentId"] == expected["chainSegmentId"]


def test_cohort_chain_link_ignores_a_roster_swap():
    """Entry/exit neutrality holds on the fast path too (section 44)."""
    history = build_chain_linked_history_from_cohorts([
        {"marketDate": "2026-01-01", "constituentCount": 2, "eligibleUniverseCount": 2,
         "basketValue": 150.0, "commonCount": 0,
         "commonCurrentValue": 0.0, "commonPreviousValue": 0.0},
        # B leaves at 50, C enters at 900 -- the surviving card A is flat.
        {"marketDate": "2026-01-02", "constituentCount": 2, "eligibleUniverseCount": 2,
         "basketValue": 1000.0, "commonCount": 1,
         "commonCurrentValue": 100.0, "commonPreviousValue": 100.0},
    ])
    assert history[1]["normalizedIndexValue"] == pytest.approx(history[0]["normalizedIndexValue"])
    # Tracked Value, by contrast, is expected to jump.
    assert history[1]["basketValue"] > history[0]["basketValue"]


def test_a_cohort_break_starts_a_new_chain_segment():
    history = build_chain_linked_history_from_cohorts([
        {"marketDate": "2026-01-01", "constituentCount": 1, "eligibleUniverseCount": 1,
         "basketValue": 100.0, "commonCount": 0,
         "commonCurrentValue": 0.0, "commonPreviousValue": 0.0},
        {"marketDate": "2026-01-02", "constituentCount": 1, "eligibleUniverseCount": 1,
         "basketValue": 900.0, "commonCount": 0,
         "commonCurrentValue": 0.0, "commonPreviousValue": 0.0},
    ])
    assert [row["chainSegmentId"] for row in history] == [0, 1]
    # The break must NOT manufacture a return out of the level difference.
    assert history[1]["normalizedIndexValue"] == pytest.approx(100.0)
    assert history[1]["dailyReturn"] is None


# ---------------------------------------------------------------------------
# Asset awareness (Phase 3F)
#
# The spec became generic over the asset. These tests pin the properties that
# make one engine safe to share: an asset cannot borrow another's segment
# vocabulary, two assets cannot collide on one identity, and ranking behaves
# identically whatever a constituent happens to be called.
# ---------------------------------------------------------------------------

from backend.domain.pokemon.market_explorer_query import (  # noqa: E402
    ASSET_CARDS,
    ASSET_MODE_LABELS,
    ASSET_SEALED,
    build_query_observations,
    rank_constituents,
    segment_vocabulary,
)


def test_sealed_is_a_supported_asset():
    spec = normalize_query_spec(mode=MODE_ALL, asset=ASSET_SEALED, segment_ids=["eliteTrainerBox"])
    assert spec["asset"] == ASSET_SEALED
    assert spec["segmentIds"] == ("eliteTrainerBox",)


def test_a_card_rarity_is_not_a_valid_sealed_segment():
    with pytest.raises(MarketExplorerQueryError):
        normalize_query_spec(
            mode=MODE_ALL, asset=ASSET_SEALED, segment_ids=["specialIllustrationRare"],
        )


def test_a_sealed_family_is_not_a_valid_card_segment():
    with pytest.raises(MarketExplorerQueryError):
        normalize_query_spec(mode=MODE_ALL, asset=ASSET_CARDS, segment_ids=["eliteTrainerBox"])


def test_an_unknown_product_family_is_rejected():
    with pytest.raises(MarketExplorerQueryError):
        normalize_query_spec(mode=MODE_ALL, asset=ASSET_SEALED, segment_ids=["jumboBox"])


def test_the_residual_is_not_a_selectable_sealed_segment():
    # otherSealed is a reconciliation bucket, not a market anyone can request.
    with pytest.raises(MarketExplorerQueryError):
        normalize_query_spec(mode=MODE_ALL, asset=ASSET_SEALED, segment_ids=["otherSealed"])


def test_segment_vocabularies_are_disjoint_between_assets():
    cards = segment_vocabulary(ASSET_CARDS)
    sealed = segment_vocabulary(ASSET_SEALED)
    assert cards and sealed
    assert not (cards & sealed), "a shared key would make one spec describe two markets"


def test_the_same_filters_on_two_assets_never_collide():
    # Identical scope, identical mode, different asset. If these fingerprinted
    # together, one asset's result would be served from the other's cache entry.
    card = normalize_query_spec(mode=MODE_ALL, asset=ASSET_CARDS)
    sealed = normalize_query_spec(mode=MODE_ALL, asset=ASSET_SEALED)
    assert query_fingerprint(card) != query_fingerprint(sealed)
    assert query_key(card) != query_key(sealed)
    assert query_key(sealed).startswith("sealed|")


def test_each_asset_names_the_modes_in_its_own_terms():
    assert ASSET_MODE_LABELS[ASSET_CARDS][MODE_CHASE] == "Chase"
    assert ASSET_MODE_LABELS[ASSET_SEALED][MODE_CHASE] == "Top 10 by Price"
    assert ASSET_MODE_LABELS[ASSET_SEALED][MODE_ALL] == "All Products"
    # The internal keys stay shared: display vocabulary must not fork the engine.
    assert set(ASSET_MODE_LABELS[ASSET_CARDS]) == set(ASSET_MODE_LABELS[ASSET_SEALED])


def test_ranking_is_identical_whatever_the_constituent_is_called():
    products = [
        {"sealedProductId": "p-cheap", "marketPrice": 10.0},
        {"sealedProductId": "p-rich", "marketPrice": 900.0},
        {"sealedProductId": "p-mid", "marketPrice": 100.0},
    ]
    ranked = rank_constituents(products, 2, id_field="sealedProductId")
    assert [row["sealedProductId"] for row in ranked] == ["p-rich", "p-mid"]
    assert [row["rank"] for row in ranked] == [1, 2]


def test_a_sealed_tie_breaks_on_product_id_not_row_order():
    tied = [
        {"sealedProductId": "bbb", "marketPrice": 50.0},
        {"sealedProductId": "aaa", "marketPrice": 50.0},
    ]
    forward = rank_constituents(tied, 1, id_field="sealedProductId")
    backward = rank_constituents(list(reversed(tied)), 1, id_field="sealedProductId")
    assert forward[0]["sealedProductId"] == "aaa"
    assert forward == backward, "membership must not depend on the order rows arrived in"


def test_sealed_membership_is_recomputed_for_every_date():
    # Product B overtakes product A on day two. The history must record exactly
    # that, never today's winner projected backward (section 52).
    rows = [
        {"marketDate": "2026-01-01", "sealedProductId": "a", "marketPrice": 100.0},
        {"marketDate": "2026-01-01", "sealedProductId": "b", "marketPrice": 50.0},
        {"marketDate": "2026-01-02", "sealedProductId": "a", "marketPrice": 100.0},
        {"marketDate": "2026-01-02", "sealedProductId": "b", "marketPrice": 200.0},
    ]
    observations = build_query_observations(
        rows, mode=MODE_CHASE, top_n=1, id_field="sealedProductId",
    )
    assert [row["constituents"][0]["setId"] for row in observations] == ["a", "b"]


def test_a_sealed_top_request_larger_than_the_universe_is_reported_not_padded():
    rows = [
        {"marketDate": "2026-01-01", "sealedProductId": f"p{index}", "marketPrice": 10.0 * index}
        for index in range(1, 8)
    ]
    observation = build_query_observations(
        rows, mode=MODE_CHASE, top_n=10, id_field="sealedProductId",
    )[0]
    assert observation["requestedTopN"] == 10
    assert observation["actualConstituentCount"] == 7
    assert len(observation["constituents"]) == 7
