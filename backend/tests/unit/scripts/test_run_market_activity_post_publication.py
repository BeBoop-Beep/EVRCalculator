from __future__ import annotations

from backend.scripts.run_market_activity_post_publication import (
    activity_coherence,
    run_post_publication,
)

SURFACE = "5caf929a-4962-4334-84a0-c75d3635135b"
OLD_SURFACE = "f01a0000-0000-4000-8000-202610010001"
MARKET = "set:7a3dd188-4375-41af-94de-c5247fe0b1a6"


class Result:
    def __init__(self, data): self.data = data
    def execute(self): return self


class Query:
    def __init__(self, client, table): self.client, self.name, self.filters = client, table, []
    def select(self, *_args): return self
    def eq(self, key, value): self.filters.append(("eq", key, value)); return self
    def in_(self, key, value): self.filters.append(("in", key, set(value))); return self
    def limit(self, _value): return self
    def execute(self):
        rows = [dict(row) for row in self.client.tables.get(self.name, [])]
        for kind, key, value in self.filters:
            rows = [row for row in rows if (row.get(key) == value if kind == "eq" else row.get(key) in value)]
        return Result(rows)


class Client:
    def __init__(self):
        self.promotions = []
        self.tables = {
            "pokemon_market_explorer_surface_serving_v2": [{"singleton": 1, "generation_id": SURFACE}],
            "pokemon_market_explorer_surface_generations_v2": [{"generation_id": SURFACE, "market_date": "2026-10-02", "state": "VALIDATED"}],
            "market_activity_market_serving_v1": [{"market_key": MARKET, "activity_generation_id": "old"}],
            "market_activity_generations_v1": [{"activity_generation_id": "old", "surface_generation_id": OLD_SURFACE, "state": "VALIDATED", "serving_state": "SERVING", "as_of": "2026-10-01"}],
        }
    def table(self, name): return Query(self, name)
    def rpc(self, name, args):
        assert name == "promote_market_activity_generation_v1"
        generation_id = args["p_activity_generation_id"]
        self.promotions.append(generation_id)
        for row in self.tables["market_activity_generations_v1"]:
            row["serving_state"] = "SERVING" if row["activity_generation_id"] == generation_id else "RETAINED"
        self.tables["market_activity_market_serving_v1"][0]["activity_generation_id"] = generation_id
        return Result(True)


class Builder:
    def __init__(self, client, state="VALIDATED"): self.client, self.state = client, state
    def build(self, market_key, *, as_of, generation_id):
        if self.state == "VALIDATED":
            self.client.tables["market_activity_generations_v1"].append({
                "activity_generation_id": generation_id, "surface_generation_id": SURFACE,
                "state": "VALIDATED", "serving_state": "RETAINED", "as_of": as_of,
            })
        return {"generationId": generation_id, "state": self.state, "diagnostics": {}}


def test_check_mode_reports_mismatch_without_writes():
    client = Client()
    result = run_post_publication(client, commit=False)
    assert result["reports"] == [{"marketKey": MARKET, "status": "unavailable_pending_refresh"}]
    assert not client.promotions


def test_validated_replacement_is_promoted_and_second_run_is_idempotent():
    client = Client()
    first = run_post_publication(client, commit=True, builder_factory=lambda _market: Builder(client))
    assert first["reports"][0]["status"] == "promoted"
    assert first["after"]["coherentMarketCount"] == 1
    second = run_post_publication(client, commit=True, builder_factory=lambda _market: Builder(client))
    assert second["reports"] == []
    assert len(client.promotions) == 1


def test_validation_failure_never_promotes_or_replaces_serving():
    client = Client()
    result = run_post_publication(client, commit=True, builder_factory=lambda _market: Builder(client, "REJECTED"))
    assert result["reports"][0]["status"] == "validation_failed"
    assert not client.promotions
    assert client.tables["market_activity_market_serving_v1"][0]["activity_generation_id"] == "old"


def test_surface_move_after_build_fails_closed():
    client = Client()
    class MovingBuilder(Builder):
        def build(self, *args, **kwargs):
            result = super().build(*args, **kwargs)
            client.tables["pokemon_market_explorer_surface_serving_v2"][0]["generation_id"] = "newer"
            client.tables["pokemon_market_explorer_surface_generations_v2"].append({"generation_id": "newer", "market_date": "2026-10-03", "state": "VALIDATED"})
            return result
    result = run_post_publication(client, commit=True, builder_factory=lambda _market: MovingBuilder(client))
    assert result["reports"][0]["status"] == "surface_moved"
    assert not client.promotions


def test_activity_coherence_requires_surface_and_date_match():
    receipt = activity_coherence(Client())
    assert receipt["supportedMarketCount"] == 1
    assert receipt["coherentMarketCount"] == 0
