"""Contract tests for the global Market root authority and daily index cutover."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.db.services.pokemon_market_rollout_cohort import (
    MARKET_ANNOTATION_VIEW_V2,
    MARKET_CERTIFICATION_COLUMNS,
    MARKET_CERTIFICATION_VIEW,
    MARKET_MEMBERSHIP_COLUMNS,
    MARKET_READY_VIEW,
    MARKET_ROOT_AUTHORITY_CUTOVER_DATE,
    resolve_market_root_cohort,
)
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

    def select(self, columns="*", **_k):
        self._client.selects.append((self._name, columns))
        available = self._client.schemas.get(self._name)
        requested = {part.strip() for part in columns.split(",")}
        if available is not None and columns != "*" and not requested <= available:
            missing = sorted(requested - available)
            raise RuntimeError(f"column {self._name}.{missing[0]} does not exist")
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
    def __init__(self, rows, *, schemas=None):
        self.rows = {name: list(vals) for name, vals in rows.items()}
        self.upserted: dict[str, list] = {}
        self.selects: list[tuple[str, str]] = []
        self.schemas = dict(schemas or {})

    def table(self, name):
        return _FakeTable(self, name)


LEGACY_CORE = [
    {
        "id": f"core-{i}", "canonical_key": f"core-{i}", "name": f"Core Set {i}",
        "era_id": "era", "release_date": "2020-01-01",
        "logo_image_url": None, "symbol_image_url": None,
        "supports_opening_simulation": True, "parent_opening_set_id": None,
    }
    for i in range(22)
]


def _rollout_rows(prefix, count, activated_date):
    return [
        {
            "set_id": f"{prefix}-{i}", "set_name": f"{prefix}-{i}",
            "canonical_key": f"{prefix}-{i}", "era_id": "era", "era_name": "Era",
            "release_date": "2019-01-01", "logo_image_url": None, "symbol_image_url": None,
            "activated_market_date": activated_date, "coverage_pct": 100,
        }
        for i in range(count)
    ]


def _set_rows(set_ids):
    return [
        {
            "id": set_id, "name": set_id, "canonical_key": set_id,
            "era_id": "era", "release_date": "2018-01-01",
            "logo_image_url": None, "symbol_image_url": None,
            "catalog_only": False, "parent_opening_set_id": None,
            "supports_opening_simulation": False,
        }
        for set_id in set_ids
    ]


def _ready_rows(set_ids, day, *, not_ready=()):
    """Exact production publication-cohort projection (membership only)."""
    not_ready = set(not_ready)
    return [
        {
            "set_id": set_id, "set_name": set_id, "canonical_key": set_id,
            "era_name": "Era", "release_date": "2018-01-01",
            "logo_image_url": None, "symbol_image_url": None,
            "market_scope": "standard", "canonical_market_date": day,
            "market_publication_ready": set_id not in not_ready,
            "current_certification_status": (
                "PRICE_FRESHNESS_STALE" if set_id in not_ready else "CERTIFIED_CURRENT"
            ),
        }
        for set_id in set_ids
    ]


def _cert_rows(set_ids, day, *, blocked=()):
    blocked = set(blocked)
    return [
        {
            "set_id": set_id, "market_scope": "standard", "canonical_market_date": day,
            "set_value_certified": set_id not in blocked,
            "top10_certified": set_id not in blocked,
            "market_scope_certified": set_id not in blocked,
            "price_freshness_certified": set_id not in blocked,
            "current_market_scope_certified": set_id not in blocked,
            "current_certification_status": (
                "CERTIFIED_CURRENT" if set_id not in blocked else "STRUCTURAL_MISMATCH"
            ),
            "oldest_component_price_date": day,
            "newest_component_price_date": day,
            "coverage_pct": 100.0,
        }
        for set_id in set_ids
    ]


def _source_rows(set_ids, day, *, value=100.0, count=5):
    return [
        {
            "set_id": set_id, "snapshot_date": day, "set_value": value,
            "priced_card_count": count, "total_card_count": count,
            "value_scope": scope, "source": "test", "updated_at": f"{day}T00:00:00Z",
        }
        for set_id in set_ids for scope in ("standard", "top10")
    ]


def _previous_index_row(set_ids, market_date, *, index_key, value=100.0, count=5):
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
        "methodology_version": MARKET_INDEX_METHODOLOGY_VERSION,
        "normalized_index_value": 100.0,
        "basket_value": value * len(set_ids), "constituents_json": constituents,
    }


def _post_cutover_fixture(day="2026-09-09", previous_day="2026-09-08"):
    previous_ids = [f"p-{i}" for i in range(39)]
    overlap_ids = previous_ids[:34]
    prior_only_ids = previous_ids[34:]
    entered_ids = [f"n-{i}" for i in range(72)]
    ready_ids = overlap_ids + entered_ids  # 106 publication-ready roots
    final_ids = previous_ids + entered_ids  # 111 continuity-safe roots

    rows = {
        "pokemon_market_set_value_publication_cohort_v1": _ready_rows(
            final_ids, day, not_ready=prior_only_ids
        ),
        # v2 has no membership predicate at all (unlike v1's
        # market_publication_ready gate): every candidate set_id the
        # authority-table resolver asks about is present, with certification
        # carried purely as annotation.
        "pokemon_market_set_value_publication_cohort_v2": _ready_rows(
            final_ids, day, not_ready=prior_only_ids
        ),
        "pokemon_market_root_set_publication_current_certification_v1": _cert_rows(final_ids, day),
        "sets": _set_rows(final_ids),
        "eras": [{"id": "era", "name": "Era"}],
        "pokemon_set_value_daily_history": _source_rows(final_ids, day),
        "pokemon_market_index_daily_history": [
            _previous_index_row(previous_ids, previous_day, index_key="raw"),
            _previous_index_row(previous_ids, previous_day, index_key="top10"),
        ],
        "pokemon_market_public_rollout_root_sets_v1": [],
        # 2026-09-10+ resolves membership from the frozen authority table, not
        # from this fixture's certification-derived continuity math. Seed it
        # with the full 111-id continuity-safe set so tests that exercise the
        # generic "day after cutover" mechanics (unrelated to the real,
        # human-approved Sep 10 106-id snapshot) keep the same fixture shape.
        "pokemon_market_root_authority": [
            {"set_id": set_id, "activated_market_date": "2026-09-09",
             "deactivated_market_date": None, "enabled": True}
            for set_id in final_ids
        ],
    }
    schemas = {
        MARKET_READY_VIEW: set(MARKET_MEMBERSHIP_COLUMNS.split(",")),
        MARKET_ANNOTATION_VIEW_V2: set(MARKET_MEMBERSHIP_COLUMNS.split(",")),
        MARKET_CERTIFICATION_VIEW: set(MARKET_CERTIFICATION_COLUMNS.split(",")),
    }
    return _FakeClient(rows, schemas=schemas), previous_ids, ready_ids, prior_only_ids, entered_ids, final_ids


def test_cutover_date_is_frozen_after_already_published_sep8():
    assert MARKET_ROOT_AUTHORITY_CUTOVER_DATE == "2026-09-09"


def test_membership_query_does_not_request_certification_columns():
    """Regression for production PostgREST 42703 on the membership view."""
    client, *_ = _post_cutover_fixture(day="2026-09-10", previous_day="2026-09-09")

    cohort = resolve_market_root_cohort(client, market_date="2026-09-10")

    selects = dict(client.selects)
    # Sep 10+ resolves via the authority table and only ever fetches
    # metadata/certification annotation from the ungated v2 view -- never
    # MARKET_READY_VIEW (v1), which still carries the market_publication_ready
    # gate and rollout-override CTE this pass exists to remove from the Sep
    # 10+ path.
    assert selects[MARKET_ANNOTATION_VIEW_V2] == MARKET_MEMBERSHIP_COLUMNS
    assert MARKET_READY_VIEW not in selects
    assert selects[MARKET_CERTIFICATION_VIEW] == MARKET_CERTIFICATION_COLUMNS
    assert cohort[0]["market_oldest_component_price_date"] == "2026-09-10"
    assert cohort[0]["market_newest_component_price_date"] == "2026-09-10"
    assert cohort[0]["market_coverage_pct"] == 100.0


def test_membership_and_certification_authority_columns_remain_separate():
    membership = set(MARKET_MEMBERSHIP_COLUMNS.split(","))
    certification_metadata = {
        "oldest_component_price_date",
        "newest_component_price_date",
        "top10_certified",
        "coverage_pct",
    }

    assert membership.isdisjoint(certification_metadata)
    assert certification_metadata <= set(MARKET_CERTIFICATION_COLUMNS.split(","))


@pytest.mark.parametrize("migration_path", [
    "backend/db/migrations/20260906004022_add_staged_market_set_value_publication_cohort.sql",
    "supabase/migrations/20260906004022_add_staged_market_set_value_publication_cohort.sql",
])
def test_membership_query_matches_deployed_view_schema_contract(migration_path):
    """Pin the service projection to the actual forward migration contract."""
    root = Path(__file__).resolve().parents[5]
    sql = (root / migration_path).read_text(encoding="utf-8")
    match = re.search(
        r"SELECT DISTINCT ON \(set_id\)\s+(.*?)\s+FROM \(", sql,
        flags=re.IGNORECASE | re.DOTALL,
    )

    assert match is not None
    deployed_columns = ",".join(
        part.strip() for part in match.group(1).replace("\n", " ").split(",")
    )
    assert MARKET_MEMBERSHIP_COLUMNS == deployed_columns


def test_pre_cutover_history_still_reconstructs_the_staged_39_roots():
    rollout = _rollout_rows("swsh", 17, "2026-09-05")
    client = _FakeClient({
        "sets": LEGACY_CORE,
        "pokemon_market_public_rollout_root_sets_v1": rollout,
        "eras": [{"id": "era", "name": "Era"}],
    })
    cohort = resolve_market_root_cohort(client, market_date="2026-09-08")
    assert len(cohort) == 39


def test_post_cutover_authority_preserves_structurally_valid_prior_roots():
    """Membership != certification: the cohort is the full canonical root
    universe. A prior-only root that is currently not-ready still belongs to
    the cohort -- annotated, never dropped."""
    client, previous_ids, ready_ids, prior_only_ids, entered_ids, final_ids = _post_cutover_fixture()

    cohort = resolve_market_root_cohort(client, market_date="2026-09-09")
    by_id = {row["id"]: row for row in cohort}

    assert len(ready_ids) == 106
    assert len(previous_ids) == 39
    assert len(final_ids) == 111
    assert len(cohort) == 111
    assert set(by_id) == set(final_ids)
    assert all(by_id[set_id]["market_publication_ready"] is False for set_id in prior_only_ids)
    assert all(by_id[set_id]["market_publication_ready"] is True for set_id in ready_ids)
    assert len(entered_ids) == 72


def test_activation_day_chain_links_only_the_39_prior_roots():
    client, previous_ids, _ready_ids, _prior_only, entered_ids, final_ids = _post_cutover_fixture()

    rows = build_rollout_market_index_rows(client, market_date="2026-09-09")
    by_key = {row["index_key"]: row for row in rows}

    for index_key in ("raw", "top10"):
        row = by_key[index_key]
        assert row["set_count"] == 111
        assert row["previous_market_date"] == "2026-09-08"
        assert set(row["diagnostics_json"]["commonSetIds"]) == set(previous_ids)
        assert set(row["diagnostics_json"]["membershipEnteredSetIds"]) == set(entered_ids)
        assert set(row["diagnostics_json"]["rolloutNeutralizedSetIds"]) == set(entered_ids)
        assert row["diagnostics_json"]["authorityTransition"] is True
        assert row["daily_return"] == pytest.approx(0.0)
        assert row["normalized_index_value"] == pytest.approx(100.0)
        assert {item["setId"] for item in row["constituents_json"]} == set(final_ids)


def test_day_after_cutover_uses_all_111_as_the_common_cohort():
    client, _previous_ids, ready_ids, prior_only_ids, entered_ids, final_ids = _post_cutover_fixture(
        day="2026-09-10", previous_day="2026-09-09"
    )
    # Replace the prior index rows with the full post-cutover basket.
    client.rows["pokemon_market_index_daily_history"] = [
        _previous_index_row(final_ids, "2026-09-09", index_key="raw"),
        _previous_index_row(final_ids, "2026-09-09", index_key="top10"),
    ]

    rows = build_rollout_market_index_rows(client, market_date="2026-09-10")
    for row in rows:
        assert row["set_count"] == 111
        assert set(row["diagnostics_json"]["commonSetIds"]) == set(final_ids)
        assert row["diagnostics_json"]["membershipEnteredSetIds"] == []
        assert row["diagnostics_json"]["authorityTransition"] is False

    cohort = resolve_market_root_cohort(client, market_date="2026-09-10")
    assert len(cohort) == len(ready_ids) + len(prior_only_ids) == 111
    assert len(entered_ids) == 72


def test_structurally_invalid_prior_only_root_is_annotated_not_dropped():
    """A structurally-invalid root stays in the cohort (membership != certification);
    it is only annotated as not-structurally-certified."""
    client, previous_ids, ready_ids, prior_only_ids, entered_ids, final_ids = _post_cutover_fixture()
    blocked = prior_only_ids[0]
    client.rows["pokemon_market_root_set_publication_current_certification_v1"] = _cert_rows(
        final_ids, "2026-09-09", blocked=[blocked]
    )

    cohort = resolve_market_root_cohort(client, market_date="2026-09-09")
    by_id = {row["id"]: row for row in cohort}
    assert blocked in by_id
    assert len(cohort) == 111
    assert by_id[blocked]["market_structural_certified"] is False
    assert blocked in previous_ids
    assert blocked not in ready_ids
    assert len(entered_ids) == 72


def test_approved_ready_root_with_failed_certification_is_annotated_not_blocked():
    """A previously-ready root that fails certification stays discoverable
    on the Market page, carrying its failed certification as annotation
    metadata instead of raising and blocking the whole cohort."""
    client, _previous_ids, ready_ids, _prior_only_ids, _entered_ids, final_ids = _post_cutover_fixture()
    blocked = ready_ids[0]
    client.rows["pokemon_market_root_set_publication_current_certification_v1"] = _cert_rows(
        final_ids, "2026-09-09", blocked=[blocked]
    )

    cohort = resolve_market_root_cohort(client, market_date="2026-09-09")
    by_id = {row["id"]: row for row in cohort}
    assert blocked in by_id
    assert len(cohort) == 111
    assert by_id[blocked]["market_structural_certified"] is False


def test_persist_rollout_rows_uses_market_index_table():
    client, *_ = _post_cutover_fixture()
    rows = build_rollout_market_index_rows(client, market_date="2026-09-09")
    assert persist_rollout_market_index_rows(client, rows) == 2
    assert len(client.upserted["pokemon_market_index_daily_history"]) == 2
