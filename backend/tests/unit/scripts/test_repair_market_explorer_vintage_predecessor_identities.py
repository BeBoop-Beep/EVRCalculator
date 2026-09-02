from backend.scripts.repair_market_explorer_vintage_predecessor_identities import (
    CACHE_STATE_TABLE,
    CACHE_TABLE,
    MERGE_LEDGER_TABLE,
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
            return Response(len(self.params["p_set_ids"]))
        if self.name == "reproject_pokemon_market_explorer_card_daily_states":
            return Response(len(self.params["p_predecessor_variant_ids"]))
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


def _base_store(*, sets, cards, variants, observations=None, cache_rows=None, cache_state=None):
    return {
        "sets": [dict(row) for row in sets],
        "cards": [dict(row) for row in cards],
        "card_variants": [dict(row) for row in variants],
        "card_variant_price_observations": [dict(row) for row in (observations or [])],
        MERGE_LEDGER_TABLE: [],
        CACHE_TABLE: [dict(row) for row in (cache_rows or [])],
        CACHE_STATE_TABLE: [dict(row) for row in (cache_state or [{"asset": "cards", "repair_generation": 5}])],
        "card_variant_price_monthly_rollups": [],
        "card_market_top_hits_by_edition_latest": [],
        "pokemon_market_explorer_card_daily_states": [],
    }


def _fossil_fixture(edition="first"):
    sets = [{"id": "fossil", "name": "Fossil"}]
    cards = [{"id": "c1", "set_id": "fossil", "name": "Zapdos", "card_number": "15"}]
    variants = [
        {"id": "v-pred-1", "card_id": "c1", "edition": None},
        {"id": "v-succ-1", "card_id": "c1", "edition": edition},
    ]
    return sets, cards, variants


def test_clean_generic_to_first_edition_mapping_resolves():
    sets, cards, variants = _fossil_fixture(edition="first")
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants))
    report = run_repair(client, commit=False, set_ids=["fossil"])
    assert report["mappings_resolved"] == 1
    assert report["mappings_by_edition"] == {"first": 1}
    assert report["ambiguous_rejections"] == 0


def test_generic_to_unlimited_mapping_resolves():
    sets, cards, variants = _fossil_fixture(edition="unlimited")
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants))
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
    return _base_store(sets=sets, cards=cards, variants=variants, observations=observations)


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
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants))
    first = run_repair(client, commit=True, set_ids=["fossil"])
    assert first["mappings_resolved"] == 1
    assert first["variants_retired"] == 1

    second = run_repair(client, commit=True, set_ids=["fossil"])
    assert second["mappings_resolved"] == 0
    assert second["already_merged_skipped"] == 1
    assert second["variants_retired"] == 0
    assert len(client.store[MERGE_LEDGER_TABLE]) == 1


def test_does_not_touch_forbidden_reference_tables():
    sets, cards, variants = _fossil_fixture(edition="first")
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants))
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
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants))
    report = run_repair(client, commit=False, set_ids=["fossil", "neo-genesis", "gym-heroes"])
    assert set(report["pilot_projection_rows_touched"]) == {"Fossil", "Neo Genesis"}


def test_targeted_cache_invalidation_only_touches_affected_caches():
    sets, cards, variants = _fossil_fixture(edition="first")
    cache_rows = [
        {"query_fingerprint": "fp-fossil-only", "status": "ready",
         "normalized_spec": {"setIds": ["fossil"]}},
        {"query_fingerprint": "fp-mixed", "status": "ready",
         "normalized_spec": {"setIds": ["fossil", "neo-genesis"]}},
        {"query_fingerprint": "fp-unrelated", "status": "ready",
         "normalized_spec": {"setIds": ["gym-heroes"]}},
    ]
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants, cache_rows=cache_rows))
    report = run_repair(client, commit=True, set_ids=["fossil"])
    assert report["cache_entries_invalidated"] == 2
    statuses = {row["query_fingerprint"]: row["status"] for row in client.store[CACHE_TABLE]}
    assert statuses["fp-fossil-only"] == "stale"
    assert statuses["fp-mixed"] == "stale"
    assert statuses["fp-unrelated"] == "ready"


def test_repair_generation_increments_appropriately():
    sets, cards, variants = _fossil_fixture(edition="first")
    client = FakeClient(_base_store(sets=sets, cards=cards, variants=variants,
                                    cache_state=[{"asset": "cards", "repair_generation": 5}]))
    report = run_repair(client, commit=True, set_ids=["fossil"])
    assert report["repair_generation_after"] == 6
    stored = next(row for row in client.store[CACHE_STATE_TABLE] if row["asset"] == "cards")
    assert stored["repair_generation"] == 6
