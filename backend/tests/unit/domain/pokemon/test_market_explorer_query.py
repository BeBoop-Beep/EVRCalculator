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
    normalize_query_spec,
    query_fingerprint,
    query_key,
    rank_chase_constituents,
)


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
    spec = normalize_query_spec(mode=MODE_ALL, era_ids=["b", "a", "b"], segment_ids=["z", "a"])
    assert spec["eraIds"] == ("a", "b")
    assert spec["segmentIds"] == ("a", "z")


def test_equivalent_selections_share_one_fingerprint():
    a = normalize_query_spec(mode=MODE_CHASE, era_ids=["sv", "swsh"], segment_ids=["sir"])
    b = normalize_query_spec(mode=MODE_CHASE, era_ids=["swsh", "sv"], segment_ids=["sir"])
    assert query_fingerprint(a) == query_fingerprint(b)
    assert query_key(a) == query_key(b)


def test_differing_selections_do_not_collide():
    a = normalize_query_spec(mode=MODE_CHASE, segment_ids=["sir"])
    b = normalize_query_spec(mode=MODE_ALL, segment_ids=["sir"])
    assert query_fingerprint(a) != query_fingerprint(b)


def test_query_key_is_human_readable_and_stable():
    spec = normalize_query_spec(mode=MODE_CHASE, segment_ids=["specialIllustrationRare"])
    assert query_key(spec) == (
        "cards|era=all|set=all|segment=specialIllustrationRare|mode=chase|topN=10"
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
