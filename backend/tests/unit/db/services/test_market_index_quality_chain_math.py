"""Blocker 1: a DEGRADED date must have ZERO influence on later index levels."""

import pytest

from backend.db.services.pokemon_market_index_service import build_index_rows

SETS = [
    {"id": "set-a", "canonical_key": "setA", "release_date": "2020-01-01"},
    {"id": "set-b", "canonical_key": "setB", "release_date": "2020-01-01"},
]


def _source(day, set_id, value, scope="standard"):
    return {"set_id": set_id, "snapshot_date": day, "set_value": value,
            "priced_card_count": 10, "total_card_count": 10, "value_scope": scope,
            "source": "test", "updated_at": f"{day}T00:00:00Z"}


def _rows(aug18_value):
    source_rows = []
    for scope in ("standard", "top10"):
        source_rows += [
            _source("2026-08-17", "set-a", 100.0, scope),
            _source("2026-08-17", "set-b", 100.0, scope),
            _source("2026-08-18", "set-a", aug18_value, scope),
            _source("2026-08-18", "set-b", aug18_value, scope),
            _source("2026-08-19", "set-a", 110.0, scope),
            _source("2026-08-19", "set-b", 110.0, scope),
        ]
    return source_rows


def _aug19(rows):
    return next(row for row in rows
                if row["market_date"] == "2026-08-19" and row["index_key"] == "raw")


ACCEPTED = {"2026-08-17", "2026-08-19"}


def test_degraded_date_is_excluded_before_chain_math():
    rows = build_index_rows(SETS, _rows(500.0), accepted_dates=ACCEPTED)
    dates = sorted({row["market_date"] for row in rows})
    assert dates == ["2026-08-17", "2026-08-19"], "Aug 18 must never be an observation"

    aug19 = _aug19(rows)
    assert aug19["previous_market_date"] == "2026-08-17", "Aug 17 -> Aug 19 transition"


def test_changing_the_degraded_date_cannot_move_the_later_index():
    quiet = _aug19(build_index_rows(SETS, _rows(101.0), accepted_dates=ACCEPTED))
    wild = _aug19(build_index_rows(SETS, _rows(9999.0), accepted_dates=ACCEPTED))

    assert quiet["normalized_index_value"] == wild["normalized_index_value"]
    assert quiet["daily_return"] == wild["daily_return"]
    # 100 -> 110 chained off the BASE 100.0, i.e. exactly +10%.
    assert quiet["daily_return"] == 110.0 / 100.0 - 1.0
    assert quiet["normalized_index_value"] == pytest.approx(110.0)


def test_without_the_filter_the_degraded_date_would_have_polluted_the_result():
    # Guard the guard: prove the regression above is actually load-bearing.
    unfiltered = _aug19(build_index_rows(SETS, _rows(9999.0)))
    filtered = _aug19(build_index_rows(SETS, _rows(9999.0), accepted_dates=ACCEPTED))
    assert unfiltered["normalized_index_value"] != filtered["normalized_index_value"]
    assert unfiltered["previous_market_date"] == "2026-08-18"


def test_accepted_dates_none_preserves_existing_behaviour():
    rows = build_index_rows(SETS, _rows(105.0))
    assert sorted({row["market_date"] for row in rows}) == [
        "2026-08-17", "2026-08-18", "2026-08-19"]
