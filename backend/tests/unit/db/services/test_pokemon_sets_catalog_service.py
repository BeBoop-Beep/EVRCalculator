from __future__ import annotations

import re

import pytest

from backend.db.services import pokemon_sets_catalog_service as svc


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, table_name, rows, select_log=None):
        self._table_name = table_name
        self._rows = rows
        self._select_log = select_log

    def select(self, *args, **_kwargs):
        if self._select_log is not None and args:
            self._select_log.append((self._table_name, args[0]))
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def or_(self, filter_expr, *_args, **_kwargs):
        # Mirror the real PostgREST `is_subset.is.null,is_subset.eq.false`
        # root-set-only filter used by the catalog query.
        if "is_subset" in filter_expr:
            self._rows = [
                row for row in self._rows if not row.get("is_subset")
            ]
        return self

    def ilike(self, *_args, **_kwargs):
        return self

    def in_(self, _column, values):
        wanted = set(values)
        self._rows = [row for row in self._rows if row.get("id") in wanted]
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        return FakeResult(list(self._rows))


class FakeClient:
    """Fake Supabase-like client that records RPC calls and forbids paging
    through pokemon_canonical_cards row-by-row.
    """

    def __init__(self, tcgs, sets_rows, canonical_counts_by_set):
        self._tcgs = tcgs
        self._sets_rows = sets_rows
        self._canonical_counts_by_set = canonical_counts_by_set
        self.rpc_calls = []
        self.canonical_cards_table_queries = 0
        self.select_log = []

    def table(self, name):
        if name == "tcgs":
            return FakeTableQuery(name, self._tcgs, self.select_log)
        if name == "sets":
            return FakeTableQuery(name, self._sets_rows, self.select_log)
        if name == "eras":
            return FakeTableQuery(name, [], self.select_log)
        if name == "pokemon_canonical_cards":
            self.canonical_cards_table_queries += 1
            raise AssertionError(
                "pokemon_canonical_cards must not be queried row-by-row; "
                "use the get_pokemon_canonical_card_counts_by_set RPC instead"
            )
        raise AssertionError(f"unexpected table: {name}")

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        if name == "get_pokemon_canonical_card_counts_by_set":
            requested = set(params["p_set_ids"])
            rows = [
                {"set_id": set_id, "card_count": count}
                for set_id, count in self._canonical_counts_by_set.items()
                if set_id in requested
            ]
            return FakeRpcBuilder(rows)
        raise AssertionError(f"unexpected rpc: {name}")


class FakeRpcBuilder:
    def __init__(self, rows):
        self._rows = rows

    def execute(self):
        return FakeResult(self._rows)


def _install_fake_client(monkeypatch, client):
    monkeypatch.setattr(svc, "service_read_client", client)
    monkeypatch.setattr(
        svc,
        "run_public_read_with_retry",
        lambda fn, **_kwargs: fn(client),
    )


def _base_sets_rows():
    return [
        {"id": "set-1", "name": "Alpha Set", "tcg_id": "pkmn", "era_id": None, "release_date": "2024-01-01"},
        {"id": "set-2", "name": "Beta Set", "tcg_id": "pkmn", "era_id": None, "release_date": "2023-01-01"},
        {"id": "set-3", "name": "Zero Card Set", "tcg_id": "pkmn", "era_id": None, "release_date": "2022-01-01"},
    ]


def test_card_counts_come_from_aggregate_rpc_not_full_corpus_scan(monkeypatch):
    client = FakeClient(
        tcgs=[{"id": "pkmn", "name": "Pokemon"}],
        sets_rows=_base_sets_rows(),
        canonical_counts_by_set={"set-1": 250, "set-2": 1500},
    )
    _install_fake_client(monkeypatch, client)

    payload = svc.get_pokemon_sets_catalog_payload()

    by_id = {row["id"]: row for row in payload["sets"]}
    assert by_id["set-1"]["card_count"] == 250
    # A set with >1000 canonical cards must not require app-side paging.
    assert by_id["set-2"]["card_count"] == 1500
    # A set with zero canonical cards returns 0, not null/missing.
    assert by_id["set-3"]["card_count"] == 0

    # Exactly one RPC round trip for counts (single batch), never a
    # pokemon_canonical_cards table scan.
    count_calls = [c for c in client.rpc_calls if c[0] == "get_pokemon_canonical_card_counts_by_set"]
    assert len(count_calls) == 1
    assert client.canonical_cards_table_queries == 0


def test_catalog_ordering_and_metadata_preserved(monkeypatch):
    client = FakeClient(
        tcgs=[{"id": "pkmn", "name": "Pokemon"}],
        sets_rows=_base_sets_rows(),
        canonical_counts_by_set={},
    )
    _install_fake_client(monkeypatch, client)

    payload = svc.get_pokemon_sets_catalog_payload()
    ids_in_order = [row["id"] for row in payload["sets"]]
    assert ids_in_order == ["set-1", "set-2", "set-3"]
    assert payload["meta"]["sources"]["pokemon_canonical_cards"] == "OK"


def test_no_pagination_helper_reintroduced():
    """Guard against reintroducing app-side .range() paging over the full
    canonical card corpus to compute counts."""
    source = svc.__file__
    with open(source, "r", encoding="utf-8") as fh:
        text = fh.read()
    # The service must not select bare set_id rows off pokemon_canonical_cards
    # and page through them with .range(); counts must come from the SQL
    # aggregate RPC.
    assert not re.search(r'table\("pokemon_canonical_cards"\)', text)
    assert "get_pokemon_canonical_card_counts_by_set" in text


# Columns actually present on the canonical `public.sets` table, per every
# other live reader of that table in this repo (pokemon_market_rollout_cohort
# ._CORE_SET_COLUMNS, pokemon_scrape_runtime_preflight, sets_repository,
# pokemon_era_set_sync_service's use of `abbreviation`, etc). This is a
# conservative allowlist -- it need not be exhaustive of every column that
# exists, but nothing selected by the catalog query may fall outside it.
# 42703 (`column sets.series does not exist`) is exactly the failure mode
# this guards against: a stale projection asking for columns the schema
# never had (series, official_card_count, printed_total, total_cards,
# set_code).
_CANONICAL_SETS_COLUMNS = {
    "id",
    "name",
    "canonical_key",
    "pokemon_api_set_id",
    "era_id",
    "release_date",
    "abbreviation",
    "is_subset",
    "logo_image_url",
    "symbol_image_url",
    "hero_image_url",
    "tcg_id",
    "supports_opening_simulation",
    "parent_opening_set_id",
    "subset_type",
    "counts_toward_parent_set_value",
    "counts_toward_parent_opening",
    "card_details_url",
    "has_card_details_url",
    "sealed_details_url",
    "ready_for_daily_scrape",
    "catalog_only",
}

_KNOWN_NONEXISTENT_SETS_COLUMNS = {
    "series",
    "official_card_count",
    "printed_total",
    "total_cards",
    "set_code",
}


def test_sets_projection_never_requests_nonexistent_columns():
    """Regression guard for the live 42703 outage: `_SETS_PROJECTION` must
    only ever request columns that actually exist on `public.sets`.

    This must fail loudly if the projection regains any of the columns that
    caused GET /tcgs/pokemon/sets to 500 in production, or any other column
    outside the verified canonical allowlist.
    """
    requested = {col.strip() for col in svc._SETS_PROJECTION.split(",")}

    overlap_with_known_bad = requested & _KNOWN_NONEXISTENT_SETS_COLUMNS
    assert not overlap_with_known_bad, (
        f"catalog projection re-introduced nonexistent sets column(s): {overlap_with_known_bad}"
    )

    unverified = requested - _CANONICAL_SETS_COLUMNS
    assert not unverified, (
        f"catalog projection requests column(s) not verified against the canonical "
        f"sets schema: {unverified}. Verify against backend/db/migrations and other "
        f"readers of the sets table before adding to _CANONICAL_SETS_COLUMNS."
    )


def test_catalog_query_filters_to_root_sets_only(monkeypatch):
    """Catalog membership is COALESCE(is_subset, false) = false -- canonical
    root sets -- regardless of RIP/simulation support or Rankings
    publication membership. A subset entry must never appear."""
    rows = [
        {"id": "root-1", "name": "Team Up", "tcg_id": "pkmn", "era_id": None,
         "release_date": "2019-02-01", "is_subset": False},
        {"id": "root-2", "name": "Cosmic Eclipse", "tcg_id": "pkmn", "era_id": None,
         "release_date": "2019-11-01", "is_subset": None},
        {"id": "subset-1", "name": "Some Subset", "tcg_id": "pkmn", "era_id": None,
         "release_date": "2020-01-01", "is_subset": True},
    ]
    client = FakeClient(
        tcgs=[{"id": "pkmn", "name": "Pokemon"}],
        sets_rows=rows,
        canonical_counts_by_set={},
    )
    _install_fake_client(monkeypatch, client)

    payload = svc.get_pokemon_sets_catalog_payload()

    ids = {row["id"] for row in payload["sets"]}
    assert ids == {"root-1", "root-2"}
    assert "subset-1" not in ids


def test_catalog_not_gated_on_rip_or_rankings_support(monkeypatch):
    """A canonical root set with no RIP/simulation support must still appear
    in the catalog -- catalog membership != RIP eligibility != Market
    eligibility. Team Up and Cosmic Eclipse in particular must be present
    even though they carry no `supports_opening_simulation` flag here."""
    rows = [
        {"id": "team-up", "name": "Team Up", "tcg_id": "pkmn", "era_id": None,
         "release_date": "2019-02-01", "is_subset": False},
        {"id": "cosmic-eclipse", "name": "Cosmic Eclipse", "tcg_id": "pkmn", "era_id": None,
         "release_date": "2019-11-01", "is_subset": False},
    ]
    client = FakeClient(
        tcgs=[{"id": "pkmn", "name": "Pokemon"}],
        sets_rows=rows,
        canonical_counts_by_set={},
    )
    _install_fake_client(monkeypatch, client)

    payload = svc.get_pokemon_sets_catalog_payload()

    names = {row["name"] for row in payload["sets"]}
    assert "Team Up" in names
    assert "Cosmic Eclipse" in names
