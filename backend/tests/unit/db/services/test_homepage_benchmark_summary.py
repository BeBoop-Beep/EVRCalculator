from types import SimpleNamespace

from backend.db.services import pokemon_public_snapshot_service as service


class Query:
    def __init__(self, data): self.data = data
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def order(self, *_args, **_kwargs): return self
    def limit(self, *_args): return self
    def in_(self, *_args): return self
    def execute(self): return SimpleNamespace(data=self.data)


class Client:
    def table(self, name):
        if name == "pokemon_rip_benchmark_publications_v1":
            return Query([{"id": "pub-1", "market_date": "2026-09-25", "overall_model_version": "overall-rip-v12"}])
        assert name == "pokemon_rip_benchmark_rows_v1"
        return Query([
            {"entity_type": "set", "entity_id": "a", "metric_key": "overall", "benchmark_score": 6.4, "rank": 1, "cohort_size": 2, "benchmark_status": "available", "source_market_date": "2026-09-25", "source_model_version": "overall-rip-v12"},
            {"entity_type": "set", "entity_id": "b", "metric_key": "overall", "benchmark_score": 9.9, "rank": 2, "cohort_size": 2, "benchmark_status": "available", "source_market_date": "2026-09-25", "source_model_version": "overall-rip-v12"},
        ])


def test_homepage_uses_canonical_benchmark_rank_and_narrow_projection(monkeypatch):
    monkeypatch.setattr(service, "get_pokemon_homepage_rankings_summary_payload", lambda limit: {
        "targets": [
            {"target_id": "b", "name": "High rounded score", "setRipV1": {"rank": 1, "score": 100, "tier": "S"}},
            {"target_id": "a", "name": "Canonical rank one", "setRipV1": {"rank": 9, "score": 1, "tier": "F"}},
        ], "meta": {"snapshot": {"builtAt": "2026-09-25T00:00:00Z"}, "ripWeightsConfig": {"private": "no"}},
    })
    contract = SimpleNamespace(benchmark_key="benchmark", calibration_version="calibration")
    payload = service.get_pokemon_homepage_benchmark_summary_payload(Client(), contract)
    assert [row["target_id"] for row in payload["targets"]] == ["a", "b"]
    assert payload["targets"][0]["benchmarkOverall"]["score"] == 6.4
    assert "tier" not in payload["targets"][0]["benchmarkOverall"]
    assert payload["benchmark"]["publicationId"] == "pub-1"
    assert payload["meta"] == {"snapshot": {"builtAt": "2026-09-25T00:00:00Z"}, "comparisonSnapshots": {}}
    assert "ripWeightsConfig" not in payload["meta"]
