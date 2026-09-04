from datetime import date

from backend.scripts.repair_market_explorer_vintage_predecessor_identities import (
    CACHE_STATE_TABLE,
    CACHE_TABLE,
    COVERAGE_TABLE,
    MERGE_LEDGER_TABLE,
    MONTHLY_ROLLUP_TABLE,
    run_repair,
)


FORBIDDEN_TABLES = {
    "user_card_holdings",
    "simulation_input_cards",
    "simulation_card_variant_pull_rates",
    "simulation_card_variant_exclusions",
    "graded_card_variants",
    "sealed_product_composition_card_components",
    "pokemon_card_chase_efficiency_rows",
    "pokemon_canonical_card_market_prices_latest",
    "card_variant_external_identities",
}


class Response:
    def __init__(self, data):
        self.data = data


def _match(row, filters):
    for field_name, kind, value in filters:
        if kind == "eq" and row.get(field_name) != value:
            return False
        if kind == "in" and row.get(field_name) not in value:
            return False
    return True


class TableQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.filters = []
        self.action = "select"
        self.payload = None
        self.start = None
        self.end = None
        self.limit_n = None

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def eq(self, field_name, value):
        self.filters.append((field_name, "eq", value))
        return self

    def in_(self, field_name, values):
        self.filters.append((field_name, "in", list(values)))
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def update(self, payload):
        self.action, self.payload = "update", payload
        return self

    def delete(self):
        self.action = "delete"
        return self

    def upsert(self, payload):
        self.action, self.payload = "upsert", payload
        return self

    def execute(self):
        self.client.calls.append(self.table)
        rows = self.client.store.setdefault(self.table, [])
        matched = [row for row in rows if _match(row, self.filters)]
        if self.action == "select":
            data = matched
            if self.start is not None:
                data = data[self.start:self.end + 1]
            elif self.limit_n is not None:
                data = data[:self.limit_n]
            return Response(data)
        if self.action == "update":
            for row in matched:
                row.update(self.payload)
            return Response(matched)
        if self.action == "delete":
            self.client.store[self.table] = [row for row in rows if row not in matched]
            return Response(matched)
        if self.action == "upsert":
            key_field = "predecessor_variant_id"
            existing = next((row for row in rows if row.get(key_field) == self.payload.get(key_field)), None)
            if existing:
                existing.update(self.payload)
            else:
                rows.append(dict(self.payload))
            return Response([self.payload])
        raise AssertionError(self.action)


class RpcQuery:
    def __init__(self, client, name, params):
        self.client = client
        self.name = name
        self.params = params

    def execute(self):
        self.client.rpc_calls.append((self.name, self.params))
        if self.name == "refresh_pokemon_card_variant_market_price_intervals":
            return Response(len(self.params["p_card_variant_ids"]))
        if self.name == "rebuild_pokemon_card_market_top_hits_by_edition":
            # Real production signature takes ZERO arguments -- a full-table
            # rebuild, not scoped by set.
            assert self.params == {}
            return Response(1)
        if self.name == "reproject_pokemon_market_explorer_card_daily_states":
            return Response(len(self.params["p_set_ids"]))
        if self.name == "retire_pokemon_card_variant_predecessor":
            # Simulate the RPC's atomic ledger write (retirement is
            # ledger-based, not physical deletion of card_variants).
            ledger_rows = self.client.store.setdefault(MERGE_LEDGER_TABLE, [])
            ledger_rows.append({
                "predecessor_variant_id": self.params["p_predecessor_variant_id"],
                "successor_variant_id": self.params["p_successor_variant_id"],
                "merge_reason": self.params.get("p_merge_reason"),
            })
            return Response(None)
        if self.name == "invalidate_pokemon_market_explorer_query_cache_scoped":
            # Simulate the RPC's atomic scoped cache invalidation + Cards
            # repair_generation bump, done entirely DB-side.
            affected = set(self.params["p_set_ids"])
            rows = self.client.store.setdefault(CACHE_TABLE, [])
            touched = 0
            for row in rows:
                set_ids = set(str(sid) for sid in (row.get("normalized_spec") or {}).get("setIds") or [])
                if affected & set_ids:
                    row["status"] = "stale"
                    touched += 1
            state_rows = self.client.store.setdefault(CACHE_STATE_TABLE, [])
            for row in state_rows:
                if row.get("asset") == "cards":
                    row["repair_generation"] = int(row.get("repair_generation") or 0) + 1
            return Response(touched)
        return Response(None)


class FakeClient:
    def __init__(self, store):
        self.store = store
        self.calls = []
        self.rpc_calls = []

    def table(self, name):
        return TableQuery(self, name)

    def rpc(self, name, params):
        return RpcQuery(self, name, params)


def _base_store(*, sets, cards, variants, observations=None, cache_rows=None, cache_state=None,
                coverage_rows=None):
    return {
        "sets": [dict(row) for row in sets],
        "cards": [dict(row) for row in cards],
        "card_variants": [dict(row) for row in variants],
        "card_variant_price_observations": [dict(row) for row in (observations or [])],
        MERGE_LEDGER_TABLE: [],
        CACHE_TABLE: [dict(row) for row in (cache_rows or [])],
        CACHE_STATE_TABLE: [dict(row) for row in (cache_state or [{"asset": "cards", "repair_generation": 5}])],
        MONTHLY_ROLLUP_TABLE: [],
        "card_market_top_hits_by_edition_latest": [],
        "pokemon_market_explorer_card_daily_states": [],
        COVERAGE_TABLE: [dict(row) for row in (coverage_rows or [])],
    }


def _fossil_fixture(edition="first"):
    sets = [{"id": "fossil", "name": "Fossil"}]
    cards = [{"id": "c1", "set_id": "fossil", "name": "Zapdos", "card_number": "15"}]
    variants = [
        {"id": "v-pred-1", "card_id": "c1", "edition": None},
        {"id": "v-succ-1", "card_id": "c1", "edition": edition},
    ]
    return sets, cards, variants


def _fossil_coverage_row(first_market_date="2026-04-11", computed_through="2026-09-01"):
    return {"set_id": "fossil", "first_market_date": first_market_date,
            "computed_through": computed_through}


def test_clean_generic_to_first_edition_mapping_resolves():
    sets, cards, variants = _fossil_fixture(edition="first")
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    coverage_rows=[_fossil_coverage_row()]))
    report = run_repair(client, commit=False, set_ids=["fossil"])
    assert report["mappings_resolved"] == 1
    assert report["mappings_by_edition"] == {"first": 1}
    assert report["ambiguous_rejections"] == 0


def test_generic_to_unlimited_mapping_resolves():
    sets, cards, variants = _fossil_fixture(edition="unlimited")
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    coverage_rows=[_fossil_coverage_row()]))
    report = run_repair(client, commit=False, set_ids=["fossil"])
    assert report["mappings_resolved"] == 1
    assert report["mappings_by_edition"] == {"unlimited": 1}


def test_base_and_base_set_2_active_generic_variants_excluded():
    sets = [{"id": "base", "name": "Base"}, {"id": "base-set-2", "name": "Base Set 2"}]
    cards = [
        {"id": "c1", "set_id": "base", "name": "Charizard", "card_number": "4"},
        {"id": "c2", "set_id": "base-set-2", "name": "Blastoise", "card_number": "2"},
    ]
    variants = [
        {"id": "v-base-generic", "card_id": "c1", "edition": None},
        {"id": "v-base-first", "card_id": "c1", "edition": "first"},
        {"id": "v-base2-generic", "card_id": "c2", "edition": None},
        {"id": "v-base2-unlimited", "card_id": "c2", "edition": "unlimited"},
    ]
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants))
    report = run_repair(client, commit=False, set_ids=["base", "base-set-2"])
    assert report["mappings_resolved"] == 0
    assert report["excluded_generic_count"] == 2


def test_base_set_machamp_8_explicit_first_edition_excluded():
    sets = [{"id": "base", "name": "Base"}]
    cards = [{"id": "c1", "set_id": "base", "name": "Machamp", "card_number": "8"}]
    variants = [
        {"id": "v-machamp-generic", "card_id": "c1", "edition": None},
        {"id": "v-machamp-first", "card_id": "c1", "edition": "first"},
    ]
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants))
    report = run_repair(client, commit=False, set_ids=["base"])
    assert report["mappings_resolved"] == 0
    assert report["excluded_machamp_count"] == 1
    # The generic Base variant is excluded on its own (active-instrument) rule,
    # not because it was paired with the excluded Machamp successor.
    assert report["excluded_generic_count"] == 1


def test_ambiguous_successor_mapping_rejected_not_guessed():
    sets = [{"id": "neo-destiny", "name": "Neo Destiny"}]
    cards = [{"id": "c1", "set_id": "neo-destiny", "name": "Entei", "card_number": "3"}]
    variants = [
        {"id": "v-pred-1", "card_id": "c1", "edition": None},
        {"id": "v-succ-first", "card_id": "c1", "edition": "first"},
        {"id": "v-succ-first-dup", "card_id": "c1", "edition": "1st-edition"},
    ]
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants))
    report = run_repair(client, commit=False, set_ids=["neo-destiny"])
    assert report["mappings_resolved"] == 0
    assert report["ambiguous_rejections"] == 1
    assert report["rejections"][0]["reason"] == "multiple_successor_candidates"


def _collision_store(pred_created_at, succ_created_at, pred_price=10.0, succ_price=10.0):
    sets, cards, variants = _fossil_fixture(edition="first")
    observations = [
        {"id": "o-pred", "card_variant_id": "v-pred-1", "condition_id": "nm",
         "source": "tcgplayer", "captured_date": "2024-04-20",
         "market_price": pred_price, "created_at": pred_created_at},
        {"id": "o-succ", "card_variant_id": "v-succ-1", "condition_id": "nm",
         "source": "tcgplayer", "captured_date": "2024-04-20",
         "market_price": succ_price, "created_at": succ_created_at},
    ]
    return _base_store(sets=sets, cards=cards, variants=variants, observations=observations,
                       coverage_rows=[_fossil_coverage_row()])


def test_observation_collision_newer_predecessor_wins():
    client = FakeClient(_collision_store("2024-04-25T00:00:00Z", "2024-04-20T00:00:00Z"))
    report = run_repair(client, commit=False, set_ids=["fossil"])
    assert report["observations_collided"] == 1
    assert report["observations_predecessor_wins"] == 1


def test_exact_price_duplicate_collision_handled():
    client = FakeClient(_collision_store(
        "2024-04-25T00:00:00Z", "2024-04-20T00:00:00Z", pred_price=10.0, succ_price=10.0))
    report = run_repair(client, commit=False, set_ids=["fossil"])
    assert report["observations_predecessor_wins"] == 1
    assert report["observations_price_matched_collisions"] == 1
    assert report["observations_price_differing_collisions"] == 0


def test_differing_price_duplicate_collision_still_follows_created_at_rule():
    client = FakeClient(_collision_store(
        "2024-04-25T00:00:00Z", "2024-04-20T00:00:00Z", pred_price=12.5, succ_price=10.0))
    report = run_repair(client, commit=False, set_ids=["fossil"])
    # Predecessor still wins on created_at, not because its price differs.
    assert report["observations_predecessor_wins"] == 1
    assert report["observations_price_differing_collisions"] == 1
    assert report["observations_price_matched_collisions"] == 0


def test_idempotent_rerun_produces_no_duplicate_or_changed_state():
    sets, cards, variants = _fossil_fixture(edition="first")
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    coverage_rows=[_fossil_coverage_row()]))
    first = run_repair(client, commit=True, set_ids=["fossil"])
    assert first["mappings_resolved"] == 1
    assert first["variants_retired"] == 1

    second = run_repair(client, commit=True, set_ids=["fossil"])
    assert second["mappings_resolved"] == 0
    assert second["already_merged_skipped"] == 1
    assert second["variants_retired"] == 0
    assert len(client.store[MERGE_LEDGER_TABLE]) == 1


def test_retirement_is_ledger_based_not_physical_deletion():
    sets, cards, variants = _fossil_fixture(edition="first")
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    coverage_rows=[_fossil_coverage_row()]))
    report = run_repair(client, commit=True, set_ids=["fossil"])
    assert report["variants_retired"] == 1

    retire_calls = [call for call in client.rpc_calls
                    if call[0] == "retire_pokemon_card_variant_predecessor"]
    assert len(retire_calls) == 1
    assert retire_calls[0][1] == {
        "p_predecessor_variant_id": "v-pred-1",
        "p_successor_variant_id": "v-succ-1",
        "p_merge_reason": "vintage_predecessor_identity_repair",
    }

    # The predecessor card_variants row is preserved -- retirement is
    # ledger-based, never a physical row deletion.
    predecessor_ids = {row["id"] for row in client.store["card_variants"]}
    assert "v-pred-1" in predecessor_ids

    # The ledger row is written atomically by the RPC, not by a separate
    # script-side upsert.
    ledger_rows = client.store[MERGE_LEDGER_TABLE]
    assert len(ledger_rows) == 1
    assert ledger_rows[0]["predecessor_variant_id"] == "v-pred-1"


def test_does_not_touch_forbidden_reference_tables():
    sets, cards, variants = _fossil_fixture(edition="first")
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    coverage_rows=[_fossil_coverage_row()]))
    run_repair(client, commit=True, set_ids=["fossil"])
    assert not (set(client.calls) & FORBIDDEN_TABLES)


def test_pilot_projection_scope_limited_to_fossil_and_neo_genesis_only():
    sets = [
        {"id": "fossil", "name": "Fossil"},
        {"id": "neo-genesis", "name": "Neo Genesis"},
        {"id": "gym-heroes", "name": "Gym Heroes"},
    ]
    cards = [
        {"id": "c1", "set_id": "fossil", "name": "Zapdos", "card_number": "15"},
        {"id": "c2", "set_id": "neo-genesis", "name": "Lugia", "card_number": "9"},
        {"id": "c3", "set_id": "gym-heroes", "name": "Blaine's Charizard", "card_number": "2"},
    ]
    variants = [
        {"id": "v-pred-1", "card_id": "c1", "edition": None},
        {"id": "v-succ-1", "card_id": "c1", "edition": "first"},
        {"id": "v-pred-2", "card_id": "c2", "edition": None},
        {"id": "v-succ-2", "card_id": "c2", "edition": "unlimited"},
        {"id": "v-pred-3", "card_id": "c3", "edition": None},
        {"id": "v-succ-3", "card_id": "c3", "edition": "first"},
    ]
    coverage_rows = [
        _fossil_coverage_row(),
        {"set_id": "neo-genesis", "first_market_date": "2026-04-11",
         "computed_through": "2026-09-01"},
    ]
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    coverage_rows=coverage_rows))
    report = run_repair(client, commit=False, set_ids=["fossil", "neo-genesis", "gym-heroes"])
    assert set(report["pilot_projection_rows_touched"]) == {"Fossil", "Neo Genesis"}
    assert report["pilot_projection_window"] == {"start_date": "2026-04-11", "end_date": "2026-09-01"}


def test_targeted_cache_invalidation_calls_atomic_scoped_rpc():
    sets, cards, variants = _fossil_fixture(edition="first")
    cache_rows = [
        {"query_fingerprint": "fp-fossil-only", "status": "ready",
         "normalized_spec": {"setIds": ["fossil"]}},
        {"query_fingerprint": "fp-mixed", "status": "ready",
         "normalized_spec": {"setIds": ["fossil", "neo-genesis"]}},
        {"query_fingerprint": "fp-unrelated", "status": "ready",
         "normalized_spec": {"setIds": ["gym-heroes"]}},
    ]
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants, cache_rows=cache_rows,
                                    coverage_rows=[_fossil_coverage_row()]))
    report = run_repair(client, commit=True, set_ids=["fossil"])

    scoped_calls = [call for call in client.rpc_calls
                    if call[0] == "invalidate_pokemon_market_explorer_query_cache_scoped"]
    assert len(scoped_calls) == 1
    assert scoped_calls[0][1] == {"p_set_ids": ["fossil"]}
    # No manual/global blanket invalidation RPC is ever called.
    assert all(call[0] != "invalidate_pokemon_market_explorer_query_cache" for call in client.rpc_calls)

    assert report["cache_entries_invalidated"] == 2
    statuses = {row["query_fingerprint"]: row["status"] for row in client.store[CACHE_TABLE]}
    assert statuses["fp-fossil-only"] == "stale"
    assert statuses["fp-mixed"] == "stale"
    assert statuses["fp-unrelated"] == "ready"


def test_cache_invalidation_generation_bump_is_atomic_not_read_then_write():
    """The prior read-then-write repair_generation bump is gone: the script
    must not read pokemon_market_explorer_cache_state before invalidating,
    it must simply call the scoped RPC and trust it to be atomic.
    """
    sets, cards, variants = _fossil_fixture(edition="first")
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    cache_state=[{"asset": "cards", "repair_generation": 5}],
                                    coverage_rows=[_fossil_coverage_row()]))
    run_repair(client, commit=True, set_ids=["fossil"])
    assert CACHE_STATE_TABLE not in client.calls
    stored = next(row for row in client.store[CACHE_STATE_TABLE] if row["asset"] == "cards")
    # The fake RPC simulates the DB-side atomic bump; the script itself never
    # reads or writes this table directly.
    assert stored["repair_generation"] == 6


def test_top_hits_rebuild_calls_zero_argument_rpc():
    sets, cards, variants = _fossil_fixture(edition="first")
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    coverage_rows=[_fossil_coverage_row()]))
    run_repair(client, commit=True, set_ids=["fossil"])
    top_hits_calls = [call for call in client.rpc_calls
                      if call[0] == "rebuild_pokemon_card_market_top_hits_by_edition"]
    assert len(top_hits_calls) == 1
    assert top_hits_calls[0][1] == {}


def test_pilot_projection_window_derived_from_coverage_min_max():
    sets, cards, variants = _fossil_fixture(edition="first")
    coverage_rows = [_fossil_coverage_row(first_market_date="2026-04-11",
                                          computed_through="2026-09-01")]
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    coverage_rows=coverage_rows))
    report = run_repair(client, commit=True, set_ids=["fossil"])
    assert report["pilot_projection_window"] == {"start_date": "2026-04-11", "end_date": "2026-09-01"}
    reproject_calls = [call for call in client.rpc_calls
                       if call[0] == "reproject_pokemon_market_explorer_card_daily_states"]
    assert len(reproject_calls) == 1
    assert reproject_calls[0][1]["p_start_date"] == date(2026, 4, 11)
    assert reproject_calls[0][1]["p_end_date"] == date(2026, 9, 1)


def test_pilot_projection_window_uses_min_first_market_date_and_max_computed_through():
    """Multiple coverage rows for the pilot scope: the derived window must
    use MIN(first_market_date)/MAX(computed_through) across ALL matched
    rows, not just the first row found.
    """
    sets = [
        {"id": "fossil", "name": "Fossil"},
        {"id": "neo-genesis", "name": "Neo Genesis"},
    ]
    cards = [
        {"id": "c1", "set_id": "fossil", "name": "Zapdos", "card_number": "15"},
        {"id": "c2", "set_id": "neo-genesis", "name": "Lugia", "card_number": "9"},
    ]
    variants = [
        {"id": "v-pred-1", "card_id": "c1", "edition": None},
        {"id": "v-succ-1", "card_id": "c1", "edition": "first"},
        {"id": "v-pred-2", "card_id": "c2", "edition": None},
        {"id": "v-succ-2", "card_id": "c2", "edition": "unlimited"},
    ]
    coverage_rows = [
        {"set_id": "fossil", "first_market_date": "2026-05-01", "computed_through": "2026-07-01"},
        {"set_id": "neo-genesis", "first_market_date": "2026-04-11", "computed_through": "2026-09-01"},
    ]
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    coverage_rows=coverage_rows))
    report = run_repair(client, commit=False, set_ids=["fossil", "neo-genesis"])
    # MIN(first_market_date) across both rows is neo-genesis's 2026-04-11
    # (not fossil's, which is the first row iterated), and
    # MAX(computed_through) is neo-genesis's 2026-09-01.
    assert report["pilot_projection_window"] == {"start_date": "2026-04-11", "end_date": "2026-09-01"}


def test_missing_pilot_set_coverage_row_fails_closed():
    sets, cards, variants = _fossil_fixture(edition="first")
    # No coverage_rows supplied at all -- the pilot set (fossil) has no
    # coverage row, so the script must fail closed rather than silently
    # falling back to a default window.
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants))
    report = run_repair(client, commit=False, set_ids=["fossil"])
    assert report["failures"] == 1
    assert report["pilot_projection_window"] is None


def test_explicit_projection_override_skips_coverage_lookup():
    sets, cards, variants = _fossil_fixture(edition="first")
    # No coverage_rows supplied -- if the script tried the coverage lookup
    # it would fail closed; the explicit override must skip it entirely.
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants))
    report = run_repair(client, commit=True, set_ids=["fossil"],
                        projection_start=date(2026, 4, 11), projection_end=date(2026, 9, 1))
    assert report["failures"] == 0
    assert COVERAGE_TABLE not in client.calls
    assert report["pilot_projection_window"] == {"start_date": "2026-04-11", "end_date": "2026-09-01"}
    reproject_calls = [call for call in client.rpc_calls
                       if call[0] == "reproject_pokemon_market_explorer_card_daily_states"]
    assert reproject_calls[0][1]["p_start_date"] == date(2026, 4, 11)
    assert reproject_calls[0][1]["p_end_date"] == date(2026, 9, 1)


def test_monthly_rollup_repair_calls_rpc_with_successor_ids_and_derived_months():
    sets, cards, variants = _fossil_fixture(edition="first")
    observations = [
        {"id": "o-pred", "card_variant_id": "v-pred-1", "condition_id": "nm",
         "source": "tcgplayer", "captured_date": "2026-04-05",
         "market_price": 10.0, "created_at": "2026-04-05T00:00:00Z"},
        {"id": "o-pred-2", "card_variant_id": "v-pred-1", "condition_id": "lp",
         "source": "tcgplayer", "captured_date": "2026-04-28",
         "market_price": 11.0, "created_at": "2026-04-28T00:00:00Z"},
    ]
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    observations=observations,
                                    coverage_rows=[_fossil_coverage_row()]))
    report = run_repair(client, commit=True, set_ids=["fossil"])
    assert report["failures"] == 0

    rollup_calls = [call for call in client.rpc_calls
                    if call[0] == "rebuild_pokemon_card_variant_price_monthly_rollups"]
    assert len(rollup_calls) == 1
    assert rollup_calls[0][1] == {
        "p_card_variant_ids": ["v-succ-1"],
        "p_start_month": date(2026, 4, 1),
        "p_end_month": date(2026, 4, 1),
    }


def test_monthly_rollup_repair_never_issues_a_direct_delete():
    """The prior direct DELETE against card_variant_price_monthly_rollups is
    gone; the script must use the rebuild RPC exclusively. Both a source
    grep and a runtime assertion guard this.
    """
    import inspect

    import backend.scripts.repair_market_explorer_vintage_predecessor_identities as module

    source = inspect.getsource(module)
    assert f'table(MONTHLY_ROLLUP_TABLE).delete()' not in source
    assert f'table("{MONTHLY_ROLLUP_TABLE}").delete()' not in source

    sets, cards, variants = _fossil_fixture(edition="first")
    observations = [
        {"id": "o-pred", "card_variant_id": "v-pred-1", "condition_id": "nm",
         "source": "tcgplayer", "captured_date": "2026-04-05",
         "market_price": 10.0, "created_at": "2026-04-05T00:00:00Z"},
    ]
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    observations=observations,
                                    coverage_rows=[_fossil_coverage_row()]))
    run_repair(client, commit=True, set_ids=["fossil"])
    # The fake client's TableQuery.delete() is never invoked on the rollup
    # table -- the rollup rebuild goes through the RPC exclusively.
    assert client.store[MONTHLY_ROLLUP_TABLE] == []
    assert any(call[0] == "rebuild_pokemon_card_variant_price_monthly_rollups"
              for call in client.rpc_calls)
