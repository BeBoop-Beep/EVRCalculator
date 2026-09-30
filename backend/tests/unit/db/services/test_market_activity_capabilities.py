from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")

from backend.db.services.market_activity_v1 import discover_activity_capabilities


GEN = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SURFACE = "11111111-1111-4111-8111-111111111111"
FP = "a" * 64


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, table):
        self.client, self.table, self.filters = client, table, {}

    def select(self, *_): return self
    def eq(self, key, value): self.filters[key] = value; return self
    def in_(self, key, value): self.filters[key] = list(value); return self
    def limit(self, *_): return self

    def execute(self):
        self.client.calls += 1
        if self.table == "market_activity_serving_v1":
            return Result([] if not self.client.serving else [{"activity_generation_id": GEN}])
        if self.table == "market_activity_generations_v1":
            return Result([{"activity_generation_id": GEN, "as_of": "2026-09-29",
                            "surface_generation_id": self.client.pinned_surface, "state": self.client.state,
                            "serving_state": "SERVING"}])
        if self.table == "pokemon_market_explorer_surface_serving_v2":
            return Result([{"generation_id": self.client.surface}])
        keys = self.filters.get("market_key", [])
        if self.table == "market_activity_rosters_v1":
            return Result([{"market_key": key, "roster_revision": self.client.refs.get(key, ref(key))} for key in keys])
        if self.table == "market_activity_group_payloads_v1":
            return Result([{"market_key": key, "payload": {"evidenceFingerprint": FP}}
                           for key in keys if key not in self.client.missing_groups])
        raise AssertionError(self.table)


class Client:
    def __init__(self, *, serving=True, state="VALIDATED", surface=SURFACE, pinned_surface=SURFACE,
                 missing_groups=(), refs=None):
        self.serving, self.state, self.surface = serving, state, surface
        self.pinned_surface, self.refs = pinned_surface, refs or {}
        self.missing_groups, self.calls = set(missing_groups), 0

    def table(self, name): return Query(self, name)


def ref(key):
    return {"kind": "SURFACE_V2_GENERATION", "generationId": SURFACE, "marketKey": key}


def markets(count):
    return [{"focusKey": f"focus-{i}", "marketKey": f"set:{i}", "rosterRef": ref(f"set:{i}")}
            for i in range(count)]


def test_no_serving_generation_is_unavailable_in_one_call():
    client = Client(serving=False)
    response = discover_activity_capabilities(client, markets(1), 30)
    assert not response["capabilities"]["focus-0"]["available"]
    assert client.calls == 1


def test_exact_current_generation_and_authoritative_payload_fingerprint():
    client = Client()
    response = discover_activity_capabilities(client, markets(1), 30)
    capability = response["capabilities"]["focus-0"]
    assert capability["available"] is True
    assert capability["evidenceFingerprint"] == FP
    assert capability["rosterRef"] == ref("set:0")
    assert client.calls == 5


def test_stale_explorer_surface_and_nonvalidated_states_are_hidden():
    stale = discover_activity_capabilities(Client(surface="22222222-2222-4222-8222-222222222222"), markets(1), 30)
    building = discover_activity_capabilities(Client(state="BUILDING"), markets(1), 30)
    assert not stale["capabilities"]["focus-0"]["available"]
    assert not building["capabilities"]["focus-0"]["available"]


def test_roster_mismatch_and_missing_group_are_unavailable():
    requested = markets(2)
    requested[0]["rosterRef"] = {**requested[0]["rosterRef"], "generationId": "33333333-3333-4333-8333-333333333333"}
    response = discover_activity_capabilities(Client(missing_groups={"set:1"}), requested, 30)
    assert response["capabilities"]["focus-0"]["reasons"] == ["ROSTER_REVISION_MISMATCH"]
    assert response["capabilities"]["focus-1"]["reasons"] == ["INVALID_MARKET_KEY"]


def test_capability_batch_db_calls_are_constant_for_1_3_and_10():
    for count in (1, 3, 10):
        client = Client()
        response = discover_activity_capabilities(client, markets(count), 30)
        assert len(response["capabilities"]) == count
        assert client.calls == 5


def test_custom_requires_the_exact_published_revision_not_a_bare_fingerprint():
    custom_ref = {"kind": "QUERY_CACHE_PUBLISHED_REVISION", "queryFingerprint": "query-fp",
                  "revisionId": "44444444-4444-4444-8444-444444444444",
                  "computedThrough": "2026-09-29"}
    client = Client(pinned_surface=None, refs={"custom:one": custom_ref})
    exact = [{"focusKey": "custom", "marketKey": "custom:one", "rosterRef": custom_ref}]
    assert discover_activity_capabilities(client, exact, 30)["capabilities"]["custom"]["available"]
    bare = [{"focusKey": "custom", "marketKey": "custom:one",
             "rosterRef": {"kind": "QUERY_CACHE_PUBLISHED_REVISION", "queryFingerprint": "query-fp"}}]
    assert not discover_activity_capabilities(client, bare, 30)["capabilities"]["custom"]["available"]
