from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")

from backend.db.services.market_activity_v1 import discover_activity_capabilities


SURFACE = "11111111-1111-4111-8111-111111111111"


def generation_id(index: int) -> str:
    return f"30000000-0000-4000-8000-{index:012d}"


def ref(key: str) -> dict:
    return {"kind": "SURFACE_V2_GENERATION", "generationId": SURFACE, "marketKey": key}


def markets(count: int) -> list[dict]:
    return [{"focusKey": f"focus-{i}", "marketKey": f"set:{i}", "rosterRef": ref(f"set:{i}")}
            for i in range(count)]


class Result:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, client, table): self.client, self.table, self.filters = client, table, {}
    def select(self, *_): return self
    def eq(self, key, value): self.filters[key] = value; return self
    def in_(self, key, value): self.filters[key] = list(value); return self
    def limit(self, *_): return self

    def execute(self):
        self.client.calls += 1
        keys = self.filters.get("market_key", [])
        ids = {str(value) for value in self.filters.get("activity_generation_id", [])}
        if self.table == "market_activity_market_serving_v1":
            return Result([{"market_key": key, "activity_generation_id": self.client.serving[key]}
                           for key in keys if key in self.client.serving])
        if self.table == "market_activity_generations_v1":
            return Result([row for gen, row in self.client.generations.items() if gen in ids])
        if self.table == "pokemon_market_explorer_surface_serving_v2":
            return Result([{"generation_id": self.client.surface}])
        if self.table == "market_activity_rosters_v1":
            return Result([{"activity_generation_id": gen, "market_key": key,
                            "roster_revision": self.client.refs.get(key, ref(key))}
                           for key, gen in self.client.serving.items() if key in keys and gen in ids])
        if self.table == "market_activity_group_payloads_v1":
            # The markets deliberately share an instrument identity. Payload
            # authority remains isolated by activity generation and market.
            return Result([{"activity_generation_id": gen, "market_key": key,
                            "payload": {"evidenceFingerprint": self.client.fingerprints[key],
                                        "overlappingInstrumentKey": "card:shared:raw"}}
                           for key, gen in self.client.serving.items()
                           if key in keys and gen in ids and key not in self.client.missing_groups])
        raise AssertionError(self.table)


class Client:
    def __init__(self, count=1, *, surface=SURFACE, state="VALIDATED", missing_groups=(),
                 refs=None, pinned_surface=SURFACE):
        self.surface, self.refs, self.calls = surface, refs or {}, 0
        self.missing_groups = set(missing_groups)
        self.serving = {f"set:{i}": generation_id(i + 1) for i in range(count)}
        self.generations = {
            gen: {"activity_generation_id": gen, "as_of": "2026-09-29",
                  "surface_generation_id": pinned_surface, "state": state, "serving_state": "SERVING"}
            for gen in self.serving.values()
        }
        self.fingerprints = {key: f"{i + 1:064x}" for i, key in enumerate(self.serving)}

    def table(self, name): return Query(self, name)


def test_no_serving_generation_is_unavailable_in_one_call():
    client = Client(0)
    response = discover_activity_capabilities(client, markets(1), 30)
    assert not response["capabilities"]["focus-0"]["available"]
    assert client.calls == 1


def test_three_independently_served_markets_are_simultaneously_available():
    client = Client(3)
    response = discover_activity_capabilities(client, markets(3), 30)
    capabilities = response["capabilities"]
    assert all(capabilities[f"focus-{i}"]["available"] for i in range(3))
    assert {capabilities[f"focus-{i}"]["activityGenerationId"] for i in range(3)} == set(client.serving.values())
    assert len({capabilities[f"focus-{i}"]["evidenceFingerprint"] for i in range(3)}) == 3
    assert client.calls == 5


def test_stale_explorer_surface_and_nonvalidated_states_are_hidden():
    stale = discover_activity_capabilities(
        Client(surface="22222222-2222-4222-8222-222222222222"), markets(1), 30)
    building = discover_activity_capabilities(Client(state="BUILDING"), markets(1), 30)
    assert stale["capabilities"]["focus-0"]["reasons"] == ["GENERATION_MISMATCH"]
    assert not building["capabilities"]["focus-0"]["available"]


def test_roster_mismatch_and_missing_group_are_unavailable():
    requested = markets(2)
    requested[0]["rosterRef"] = {**requested[0]["rosterRef"],
                                  "generationId": "33333333-3333-4333-8333-333333333333"}
    response = discover_activity_capabilities(Client(2, missing_groups={"set:1"}), requested, 30)
    assert response["capabilities"]["focus-0"]["reasons"] == ["ROSTER_REVISION_MISMATCH"]
    assert response["capabilities"]["focus-1"]["reasons"] == ["INVALID_MARKET_KEY"]


def test_capability_batch_db_calls_are_constant_for_1_3_and_10_independent_generations():
    for count in (1, 3, 10):
        client = Client(count)
        response = discover_activity_capabilities(client, markets(count), 30)
        assert len(response["capabilities"]) == count
        assert all(item["available"] for item in response["capabilities"].values())
        assert client.calls == 5


def test_custom_requires_the_exact_published_revision_not_a_bare_fingerprint():
    custom_ref = {"kind": "QUERY_CACHE_PUBLISHED_REVISION", "queryFingerprint": "query-fp",
                  "revisionId": "44444444-4444-4444-8444-444444444444",
                  "computedThrough": "2026-09-29"}
    client = Client(0, pinned_surface=None)
    client.serving = {"custom:one": generation_id(1)}
    client.generations = {generation_id(1): {"activity_generation_id": generation_id(1),
        "as_of": "2026-09-29", "surface_generation_id": None,
        "state": "VALIDATED", "serving_state": "SERVING"}}
    client.refs = {"custom:one": custom_ref}
    client.fingerprints = {"custom:one": "a" * 64}
    exact = [{"focusKey": "custom", "marketKey": "custom:one", "rosterRef": custom_ref}]
    assert discover_activity_capabilities(client, exact, 30)["capabilities"]["custom"]["available"]
    bare = [{"focusKey": "custom", "marketKey": "custom:one",
             "rosterRef": {"kind": "QUERY_CACHE_PUBLISHED_REVISION", "queryFingerprint": "query-fp"}}]
    assert not discover_activity_capabilities(client, bare, 30)["capabilities"]["custom"]["available"]
