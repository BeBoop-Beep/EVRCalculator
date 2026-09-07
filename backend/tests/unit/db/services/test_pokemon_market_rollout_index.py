"""Fixture-level coverage for the canonical rollout-aware daily Market index
builder (backend/db/services/pokemon_market_rollout_index.py), backed by the
public rollout root cohort resolver
(backend/db/services/pokemon_market_rollout_cohort.py).

These are the two functions the production regression fix in
refresh_stale_public_snapshots.py now delegates to for normal daily
publication, so this file exercises the exact activation-day / day-after
semantics the fix depends on, plus a hypothetical second-era rollout to prove
nothing here is hardcoded to today's 39-root cohort.
"""

from __future__ import annotations

import pytest

from backend.db.services.pokemon_market_rollout_cohort import resolve_market_root_cohort
from backend.db.services.pokemon_market_rollout_index import (
    build_rollout_market_index_rows,
    persist_rollout_market_index_rows,
)
from backend.domain.pokemon.market_index import MARKET_INDEX_METHODOLOGY_VERSION


class _FakeTable:
    def __init__(self, client, name):
        self._client = client
        self._name = name
        self._rows = list(client.rows.get(name, []))
        self._order = None

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self._rows = [r for r in self._rows if str(r.get(field)) == str(value)]
        return self

    def lt(self, field, value):
        self._rows = [r for r in self._rows if str(r.get(field)) < str(value)]
        return self

    def lte(self, field, value):
        self._rows = [r for r in self._rows if str(r.get(field)) <= str(value)]
        return self

    def in_(self, field, values):
        values = {str(v) for v in values}
        self._rows = [r for r in self._rows if str(r.get(field)) in values]
        return self

    def order(self, field, desc=False):
        self._rows = sorted(self._rows, key=lambda r: str(r.get(field)), reverse=bool(desc))
        return self

    def limit(self, count):
        self._rows = self._rows[:count]
        return self

    def range(self, start, end):
        self._rows = self._rows[start:end + 1]
        return self

    def upsert(self, rows, **_k):
        table = self._client.rows.setdefault(self._name, [])
        for row in rows:
            table.append(dict(row))
        self._client.upserted.setdefault(self._name, []).extend(dict(r) for r in rows)
        return self

    def execute(self):
        return type("Result", (), {"data": list(self._rows)})()


class _FakeClient:
    def __init__(self, rows):
        self.rows = {name: list(vals) for name, vals in rows.items()}
        self.upserted: dict[str, list] = {}

    def table(self, name):
        return _FakeTable(self, name)


CORE_SET_COLUMNS_SETS = [
    {
        "id": f"core-{i}", "canonical_key": f"core-{i}", "name": f"Core Set {i}",
        "era_id": "era-core", "release_date": "2020-01-01",
        "logo_image_url": None, "symbol_image_url": None,
        "supports_opening_simulation": True, "parent_opening_set_id": None,
    }
    for i in range(22)
]


def _rollout_rows(prefix, count, era_id, activated_date):
    return [
        {
            "set_id": f"{prefix}-{i}", "set_name": f"{prefix.title()} Set {i}",
            "canonical_key": f"{prefix}-{i}", "era_id": era_id, "era_name": era_id,
            "release_date": "2019-01-01", "logo_image_url": None, "symbol_image_url": None,
            "activated_market_date": activated_date, "coverage_pct": 100,
        }
        for i in range(count)
    ]


def _source_rows(set_ids, day, *, value=100.0, count=5):
    rows = []
    for set_id in set_ids:
        for scope in ("standard", "top10"):
            rows.append({
                "set_id": set_id, "snapshot_date": day, "set_value": value,
                "priced_card_count": count, "total_card_count": count,
                "value_scope": scope, "source": "test", "updated_at": f"{day}T00:00:00Z",
            })
    return rows


def _previous_index_rows(set_ids, market_date, *, index_key, value=100.0, count=5):
    constituents = [
        {
            "setId": set_id, "canonicalKey": set_id, "setValue": value,
            "includedCardCount": count, "sourceSnapshotDate": market_date,
            "source": "test", "sourceUpdatedAt": f"{market_date}T00:00:00Z",
        }
        for set_id in set_ids
    ]
    return {
        "tcg": "pokemon", "index_key": index_key, "market_date": market_date,
        "methodology_version": MARKET_INDEX_METHODOLOGY_VERSION, "normalized_index_value": 100.0,
        "basket_value": value * len(set_ids), "constituents_json": constituents,
    }


def test_core_plus_rollout_cohort_is_39_roots_for_raw_and_top10():
    """Requirement 5: core-22 + rollout-17 fixture produces set_count=39."""
    core_ids = [row["id"] for row in CORE_SET_COLUMNS_SETS]
    rollout_rows = _rollout_rows("swsh", 17, "era-swsh", "2026-09-05")
    rollout_ids = [row["set_id"] for row in rollout_rows]
    day = "2026-09-06"
    all_ids = core_ids + rollout_ids

    client = _FakeClient({
        "sets": CORE_SET_COLUMNS_SETS,
        "pokemon_market_public_rollout_root_sets_v1": rollout_rows,
        "eras": [{"id": "era-core", "name": "Core"}, {"id": "era-swsh", "name": "Sword & Shield"}],
        "pokemon_set_value_daily_history": _source_rows(all_ids, day),
        "pokemon_market_index_daily_history": [
            _previous_index_rows(all_ids, "2026-09-05", index_key="raw"),
            _previous_index_rows(all_ids, "2026-09-05", index_key="top10"),
        ],
    })

    rows = build_rollout_market_index_rows(client, market_date=day)

    by_key = {row["index_key"]: row for row in rows}
    assert by_key["raw"]["set_count"] == 39
    assert by_key["top10"]["set_count"] == 39


def test_activation_day_neutralizes_rollout_roots_from_common_cohort():
    """Requirement 6: on the activation date, the 17 rollout roots are
    excluded from the common-cohort return; common_count stays at the
    original 22, and rolloutTransition is reported true."""
    core_ids = [row["id"] for row in CORE_SET_COLUMNS_SETS]
    activation_day = "2026-09-05"
    rollout_rows = _rollout_rows("swsh", 17, "era-swsh", activation_day)
    rollout_ids = [row["set_id"] for row in rollout_rows]
    all_ids = core_ids + rollout_ids

    client = _FakeClient({
        "sets": CORE_SET_COLUMNS_SETS,
        "pokemon_market_public_rollout_root_sets_v1": rollout_rows,
        "eras": [{"id": "era-core", "name": "Core"}, {"id": "era-swsh", "name": "Sword & Shield"}],
        "pokemon_set_value_daily_history": _source_rows(all_ids, activation_day),
        # Previous day (Sep 4) only had the core 22 roots persisted.
        "pokemon_market_index_daily_history": [
            _previous_index_rows(core_ids, "2026-09-04", index_key="raw"),
            _previous_index_rows(core_ids, "2026-09-04", index_key="top10"),
        ],
    })

    rows = build_rollout_market_index_rows(client, market_date=activation_day)

    by_key = {row["index_key"]: row for row in rows}
    for index_key in ("raw", "top10"):
        row = by_key[index_key]
        assert row["set_count"] == 39
        assert row["previous_market_date"] == "2026-09-04"
        assert row["diagnostics_json"]["rolloutTransition"] is True
        assert set(row["diagnostics_json"]["rolloutNeutralizedSetIds"]) == set(rollout_ids)
        common_ids = row["diagnostics_json"]["commonSetIds"]
        assert set(common_ids) == set(core_ids)
        assert len(common_ids) == 22


def test_day_after_activation_uses_all_39_as_common_cohort():
    """Requirement 7: the day after activation, cohort=39, previous
    date=activation date, common cohort=all 39, rolloutTransition=false."""
    core_ids = [row["id"] for row in CORE_SET_COLUMNS_SETS]
    activation_day = "2026-09-05"
    next_day = "2026-09-06"
    rollout_rows = _rollout_rows("swsh", 17, "era-swsh", activation_day)
    rollout_ids = [row["set_id"] for row in rollout_rows]
    all_ids = core_ids + rollout_ids

    client = _FakeClient({
        "sets": CORE_SET_COLUMNS_SETS,
        "pokemon_market_public_rollout_root_sets_v1": rollout_rows,
        "eras": [{"id": "era-core", "name": "Core"}, {"id": "era-swsh", "name": "Sword & Shield"}],
        "pokemon_set_value_daily_history": _source_rows(all_ids, next_day),
        # Previous day (Sep 5, activation) already carries all 39 roots.
        "pokemon_market_index_daily_history": [
            _previous_index_rows(all_ids, activation_day, index_key="raw"),
            _previous_index_rows(all_ids, activation_day, index_key="top10"),
        ],
    })

    rows = build_rollout_market_index_rows(client, market_date=next_day)

    by_key = {row["index_key"]: row for row in rows}
    for index_key in ("raw", "top10"):
        row = by_key[index_key]
        assert row["set_count"] == 39
        assert row["previous_market_date"] == activation_day
        assert row["diagnostics_json"]["rolloutTransition"] is False
        assert set(row["diagnostics_json"]["commonSetIds"]) == set(all_ids)


def test_mismatched_candidate_row_count_is_detectable_against_authority():
    """Requirement 8 (fixture half): resolve_market_root_cohort is the single
    source of truth a caller must compare candidate set_count against. A
    candidate cohort that only reflects the legacy 22 roots must be provably
    smaller than the authoritative cohort once rollout is active."""
    core_ids = [row["id"] for row in CORE_SET_COLUMNS_SETS]
    day = "2026-09-06"
    rollout_rows = _rollout_rows("swsh", 17, "era-swsh", "2026-09-05")

    client = _FakeClient({
        "sets": CORE_SET_COLUMNS_SETS,
        "pokemon_market_public_rollout_root_sets_v1": rollout_rows,
        "eras": [{"id": "era-core", "name": "Core"}, {"id": "era-swsh", "name": "Sword & Shield"}],
    })

    expected_root_count = len(resolve_market_root_cohort(client, market_date=day))
    legacy_candidate_set_count = len(core_ids)

    assert expected_root_count == 39
    assert legacy_candidate_set_count != expected_root_count


def test_future_second_era_rollout_dynamically_increases_expected_cohort():
    """Requirement 10: a hypothetical second era (e.g. Sun & Moon) rollout
    increases the expected cohort with nothing hardcoded to 39 anywhere in
    this call path -- resolve_market_root_cohort must simply reflect whatever
    the rollout authority currently reports active."""
    core_ids = [row["id"] for row in CORE_SET_COLUMNS_SETS]
    swsh_rows = _rollout_rows("swsh", 17, "era-swsh", "2026-09-05")
    sm_rows = _rollout_rows("sm", 11, "era-sm", "2026-12-01")
    day = "2026-12-02"

    client = _FakeClient({
        "sets": CORE_SET_COLUMNS_SETS,
        "pokemon_market_public_rollout_root_sets_v1": swsh_rows + sm_rows,
        "eras": [
            {"id": "era-core", "name": "Core"},
            {"id": "era-swsh", "name": "Sword & Shield"},
            {"id": "era-sm", "name": "Sun & Moon"},
        ],
    })

    cohort = resolve_market_root_cohort(client, market_date=day)

    # 22 core + 17 SWSH + 11 SM = 50, dynamically -- not a literal constant.
    assert len(cohort) == len(core_ids) + len(swsh_rows) + len(sm_rows) == 50
