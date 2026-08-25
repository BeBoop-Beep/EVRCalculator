"""Deterministic tests for set-level Cards Market Index and Market Breadth.

Every test here builds observations by hand rather than touching the database,
so the index/breadth mathematics is pinned independently of live market data.
"""

from __future__ import annotations

import pytest

from backend.db.services.pokemon_set_cards_market_analytics_service import (
    BREADTH_STATUS_AVAILABLE,
    BREADTH_STATUS_BASELINE_UNAVAILABLE,
    BREADTH_STATUS_INSUFFICIENT_HISTORY,
    BREADTH_STATUS_NO_COMMON_COHORT,
    PokemonSetCardsMarketAnalyticsError,
    build_cards_market_analytics_from_observations,
    build_cards_market_index,
    build_constituent_observations,
    compute_market_breadth,
    load_card_constituent_rows,
    reconcile_observations_to_set_value,
    summarize_reconciliation,
)
from backend.domain.pokemon.market_index import MARKET_INDEX_BASE_VALUE


def observations(spec):
    """{date: {card_id: price}} -> shared index observation contract."""
    return [
        {
            "marketDate": market_date,
            "constituents": [
                {"setId": card_id, "setValue": price} for card_id, price in sorted(prices.items())
            ],
        }
        for market_date, prices in sorted(spec.items())
    ]


def days(count, start_day=1, prices=None):
    return {
        f"2026-08-{start_day + offset:02d}": dict(prices or {"a": 10.0, "b": 20.0})
        for offset in range(count)
    }


# ---------------------------------------------------------------------------
# Cards Market Index
# ---------------------------------------------------------------------------


def test_index_starts_at_base_value():
    index = build_cards_market_index(observations({"2026-08-01": {"a": 10.0}}))
    assert index["history"][0]["indexValue"] == MARKET_INDEX_BASE_VALUE
    assert index["currentValue"] == MARKET_INDEX_BASE_VALUE
    assert index["segmentCount"] == 1


def test_index_is_flat_when_prices_are_stable():
    index = build_cards_market_index(
        observations({"2026-08-01": {"a": 10.0, "b": 5.0}, "2026-08-02": {"a": 10.0, "b": 5.0}})
    )
    assert [row["indexValue"] for row in index["history"]] == [100.0, 100.0]


def test_index_rises_with_rising_prices():
    index = build_cards_market_index(
        observations({"2026-08-01": {"a": 10.0}, "2026-08-02": {"a": 11.0}})
    )
    assert index["currentValue"] == pytest.approx(110.0)


def test_index_falls_with_falling_prices():
    index = build_cards_market_index(
        observations({"2026-08-01": {"a": 10.0}, "2026-08-02": {"a": 9.0}})
    )
    assert index["currentValue"] == pytest.approx(90.0)


def test_new_constituent_with_overlap_does_not_move_the_index():
    """A card entering the universe must not itself register as a price move."""
    index = build_cards_market_index(
        observations({"2026-08-01": {"a": 10.0}, "2026-08-02": {"a": 10.0, "b": 500.0}})
    )
    assert index["currentValue"] == pytest.approx(100.0)


def test_removed_constituent_with_overlap_does_not_move_the_index():
    index = build_cards_market_index(
        observations({"2026-08-01": {"a": 10.0, "b": 500.0}, "2026-08-02": {"a": 10.0}})
    )
    assert index["currentValue"] == pytest.approx(100.0)


def test_zero_overlap_starts_a_new_segment_rather_than_faking_a_return():
    index = build_cards_market_index(
        observations(
            {
                "2026-08-01": {"a": 10.0},
                "2026-08-02": {"a": 12.0},
                "2026-08-03": {"z": 99.0},
                "2026-08-04": {"z": 99.0},
            }
        )
    )
    values = [row["indexValue"] for row in index["history"]]
    assert values == [100.0, pytest.approx(120.0), 100.0, 100.0]
    assert index["segmentCount"] == 2
    assert index["currentSegmentId"] == 1
    # The break's far side is a fresh baseline, explicitly flagged.
    assert index["history"][2]["isNewSegment"] is True
    # Tracking restarts at the current segment, not the first point ever.
    assert index["trackingSince"] == "2026-08-03"


def test_all_window_never_spans_a_chain_break():
    index = build_cards_market_index(
        observations(
            {
                "2026-08-01": {"a": 10.0},
                "2026-08-02": {"a": 20.0},
                "2026-08-03": {"z": 99.0},
                "2026-08-04": {"z": 110.0},
            }
        )
    )
    since = index["movements"]["SinceTracking"]
    # Only the +11.1% inside the current segment, never 120 -> 100 as a crash.
    assert since["startDate"] == "2026-08-03"
    assert since["percent"] == pytest.approx(100.0 * (110.0 / 99.0 - 1.0))


def test_absent_card_is_excluded_not_fabricated_as_zero():
    """A missing card must not be treated as a price of zero."""
    index = build_cards_market_index(
        observations({"2026-08-01": {"a": 10.0, "b": 10.0}, "2026-08-02": {"a": 10.0}})
    )
    # Zero-filling 'b' would read as a 50% collapse; common-cohort says flat.
    assert index["currentValue"] == pytest.approx(100.0)
    assert index["history"][1]["constituentCount"] == 1


def test_seven_and_thirty_day_windows_use_shared_period_semantics():
    spec = {f"2026-08-{day:02d}": {"a": 10.0} for day in range(1, 31)}
    spec["2026-07-31"] = {"a": 10.0}
    spec["2026-08-30"] = {"a": 12.0}
    index = build_cards_market_index(observations(spec))
    seven = index["movements"]["7D"]
    thirty = index["movements"]["30D"]
    assert seven["available"] is True
    assert seven["startDate"] == "2026-08-23"
    assert seven["percent"] == pytest.approx(20.0)
    assert thirty["available"] is True
    assert thirty["startDate"] == "2026-07-31"


def test_window_unavailable_rather_than_fabricated_when_history_is_short():
    index = build_cards_market_index(
        observations({"2026-08-01": {"a": 10.0}, "2026-08-02": {"a": 11.0}})
    )
    assert index["movements"]["30D"]["available"] is False
    assert index["movements"]["30D"]["percent"] is None


def test_empty_observations_yield_no_index():
    assert build_cards_market_index([]) is None


# ---------------------------------------------------------------------------
# Market Breadth
# ---------------------------------------------------------------------------


def breadth_1d(spec):
    return compute_market_breadth(observations(spec))["1D"]


def test_breadth_all_advancing():
    result = breadth_1d(
        {"2026-08-01": {"a": 1.0, "b": 2.0}, "2026-08-02": {"a": 1.5, "b": 2.5}}
    )
    assert result["status"] == BREADTH_STATUS_AVAILABLE
    assert (result["advancingCount"], result["decliningCount"], result["unchangedCount"]) == (2, 0, 0)
    assert result["advancingPercent"] == 100.0


def test_breadth_all_declining():
    result = breadth_1d(
        {"2026-08-01": {"a": 2.0, "b": 3.0}, "2026-08-02": {"a": 1.0, "b": 2.0}}
    )
    assert (result["advancingCount"], result["decliningCount"], result["unchangedCount"]) == (0, 2, 0)
    assert result["decliningPercent"] == 100.0


def test_breadth_all_unchanged_is_exact_on_cents():
    result = breadth_1d(
        {"2026-08-01": {"a": 12.34, "b": 0.07}, "2026-08-02": {"a": 12.34, "b": 0.07}}
    )
    assert result["unchangedCount"] == 2
    assert result["advancingCount"] == 0
    assert result["decliningCount"] == 0


def test_breadth_mixed():
    result = breadth_1d(
        {
            "2026-08-01": {"a": 1.0, "b": 2.0, "c": 3.0},
            "2026-08-02": {"a": 2.0, "b": 1.0, "c": 3.0},
        }
    )
    assert (result["advancingCount"], result["decliningCount"], result["unchangedCount"]) == (1, 1, 1)
    assert result["eligibleCount"] == 3


def test_breadth_excludes_card_missing_at_baseline():
    result = breadth_1d({"2026-08-01": {"a": 1.0}, "2026-08-02": {"a": 1.0, "newcomer": 9.0}})
    assert result["eligibleCount"] == 1
    assert result["unchangedCount"] == 1


def test_breadth_excludes_card_missing_at_end():
    result = breadth_1d({"2026-08-01": {"a": 1.0, "leaver": 9.0}, "2026-08-02": {"a": 1.0}})
    assert result["eligibleCount"] == 1


def test_breadth_reports_no_common_cohort_rather_than_zeroes():
    result = breadth_1d({"2026-08-01": {"a": 1.0}, "2026-08-02": {"z": 1.0}})
    assert result["available"] is False
    assert result["status"] == BREADTH_STATUS_NO_COMMON_COHORT
    assert result["advancingPercent"] is None


def test_breadth_reports_insufficient_history_for_long_windows():
    result = compute_market_breadth(
        observations({"2026-08-01": {"a": 1.0}, "2026-08-02": {"a": 2.0}})
    )
    assert result["30D"]["status"] == BREADTH_STATUS_INSUFFICIENT_HISTORY
    assert result["30D"]["available"] is False


def test_breadth_single_point_has_no_baseline():
    """One observation yields no participation figure, by either failure mode.

    The two statuses are distinct on purpose: "1D" has no prior observation to
    resolve at all, whereas "All" resolves a baseline that turns out to BE the
    end date. Both are unavailable; neither may report 100% unchanged, which
    would assert a market fact that was never observed.
    """
    result = compute_market_breadth(observations({"2026-08-01": {"a": 1.0}}))
    assert result["1D"]["status"] == BREADTH_STATUS_INSUFFICIENT_HISTORY
    assert result["SinceTracking"]["status"] == BREADTH_STATUS_BASELINE_UNAVAILABLE
    assert all(not window["available"] for window in result.values())
    assert all(window["advancingPercent"] is None for window in result.values())


def test_breadth_windows_track_index_window_endpoints():
    spec = {f"2026-08-{day:02d}": {"a": 10.0, "b": 10.0} for day in range(1, 31)}
    spec["2026-07-31"] = {"a": 10.0, "b": 10.0}
    spec["2026-08-30"] = {"a": 12.0, "b": 8.0}
    result = compute_market_breadth(observations(spec))
    assert result["7D"]["startDate"] == "2026-08-23"
    assert result["30D"]["startDate"] == "2026-07-31"
    assert result["SinceTracking"]["startDate"] == "2026-07-31"
    assert result["7D"]["advancingCount"] == 1
    assert result["7D"]["decliningCount"] == 1


def test_breadth_percentages_always_total_one_hundred():
    """Three independently rounded shares must not total 99.9 or 100.1."""
    spec = {
        "2026-08-01": {f"c{index}": 10.0 for index in range(7)},
        "2026-08-02": {
            **{f"c{index}": 11.0 for index in range(3)},
            **{f"c{index}": 9.0 for index in range(3, 5)},
            **{f"c{index}": 10.0 for index in range(5, 7)},
        },
    }
    result = breadth_1d(spec)
    assert result["eligibleCount"] == 7
    total = result["advancingPercent"] + result["decliningPercent"] + result["unchangedPercent"]
    assert total == pytest.approx(100.0)


def test_breadth_confined_to_current_chain_segment():
    """Breadth must not compare across a break the index considers disconnected."""
    payload = build_cards_market_analytics_from_observations(
        observations(
            {
                "2026-08-01": {"a": 10.0},
                "2026-08-02": {"a": 20.0},
                "2026-08-03": {"z": 5.0},
                "2026-08-04": {"z": 6.0},
            }
        )
    )
    since = payload["marketBreadth"]["SinceTracking"]
    assert since["startDate"] == "2026-08-03"
    assert since["eligibleCount"] == 1
    assert since["advancingCount"] == 1


# ---------------------------------------------------------------------------
# Constituent shaping
# ---------------------------------------------------------------------------


def test_rows_group_into_one_observation_per_date():
    rows = [
        {"market_date": "2026-08-01", "canonical_card_id": "a", "market_price": 1.5},
        {"market_date": "2026-08-01", "canonical_card_id": "b", "market_price": 2.5},
        {"market_date": "2026-08-02", "canonical_card_id": "a", "market_price": 1.75},
    ]
    result = build_constituent_observations(rows)
    assert [row["marketDate"] for row in result] == ["2026-08-01", "2026-08-02"]
    assert len(result[0]["constituents"]) == 2


def test_non_positive_and_missing_prices_are_dropped_not_zeroed():
    rows = [
        {"market_date": "2026-08-01", "canonical_card_id": "a", "market_price": 1.5},
        {"market_date": "2026-08-01", "canonical_card_id": "b", "market_price": 0},
        {"market_date": "2026-08-01", "canonical_card_id": "c", "market_price": None},
    ]
    result = build_constituent_observations(rows)
    assert [row["setId"] for row in result[0]["constituents"]] == ["a"]


# ---------------------------------------------------------------------------
# Set Value reconciliation guard
# ---------------------------------------------------------------------------


def test_reconciliation_flags_drift_beyond_a_cent():
    obs = observations({"2026-08-01": {"a": 10.0, "b": 5.0}})
    findings = reconcile_observations_to_set_value(obs, {"2026-08-01": 15.0})
    assert findings[0]["withinTolerance"] is True
    findings = reconcile_observations_to_set_value(obs, {"2026-08-01": 99.0})
    assert findings[0]["withinTolerance"] is False
    assert summarize_reconciliation(findings)["driftDateCount"] == 1


def test_reconciliation_tolerates_one_cent():
    obs = observations({"2026-08-01": {"a": 10.0}})
    findings = reconcile_observations_to_set_value(obs, {"2026-08-01": 10.01})
    assert findings[0]["withinTolerance"] is True


# ---------------------------------------------------------------------------
# Loader chunking (the 1000-row response cap)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def execute(self):
        return _FakeResponse(self._rows)


class _FakeClient:
    """Emulates PostgREST truncating every response at db-max-rows."""

    def __init__(self, rows_by_date, cap=1000):
        self.rows_by_date = rows_by_date
        self.cap = cap
        self.calls = []

    def rpc(self, name, params):
        start, end = params["p_start_date"], params["p_end_date"]
        self.calls.append((start, end))
        rows = [
            row
            for market_date, day_rows in sorted(self.rows_by_date.items())
            if start <= market_date <= end
            for row in day_rows
        ]
        return _FakeQuery(rows[: self.cap])


def _rows_by_date(day_count, cards_per_day):
    return {
        f"2026-06-{day:02d}": [
            {"market_date": f"2026-06-{day:02d}", "canonical_card_id": f"c{index}", "market_price": 1.0}
            for index in range(cards_per_day)
        ]
        for day in range(1, day_count + 1)
    }


def test_loader_returns_every_row_despite_the_response_cap():
    rows_by_date = _rows_by_date(20, 200)  # 4000 rows, cap is 1000
    client = _FakeClient(rows_by_date)
    rows = load_card_constituent_rows("set-1", "2026-06-01", "2026-06-20", client=client)
    assert len(rows) == 4000
    # Must have split by date rather than accepting one truncated response.
    assert len(client.calls) > 1
    assert len({(row["market_date"], row["canonical_card_id"]) for row in rows}) == 4000


def test_loader_narrows_chunks_when_a_response_hits_the_cap():
    rows_by_date = _rows_by_date(8, 400)
    client = _FakeClient(rows_by_date)
    rows = load_card_constituent_rows("set-1", "2026-06-01", "2026-06-08", client=client)
    assert len(rows) == 3200


def test_loader_rejects_a_single_day_larger_than_one_response():
    rows_by_date = _rows_by_date(3, 1200)
    client = _FakeClient(rows_by_date)
    with pytest.raises(PokemonSetCardsMarketAnalyticsError):
        load_card_constituent_rows("set-1", "2026-06-01", "2026-06-03", client=client)


def test_loader_rejects_inverted_range():
    with pytest.raises(PokemonSetCardsMarketAnalyticsError):
        load_card_constituent_rows("set-1", "2026-06-05", "2026-06-01", client=_FakeClient({}))
