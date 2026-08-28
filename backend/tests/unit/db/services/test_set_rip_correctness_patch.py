from types import SimpleNamespace

import pytest

from backend.db.services import pokemon_public_snapshot_service as service


@pytest.mark.parametrize(
    "publication_fields",
    [
        {"rankingCalculationRunId": "ranking-old", "rankingUpdatedAt": "2026-08-26T00:00:00Z"},
        {"meta": {"rankingCalculationRunId": "ranking-old", "rankingUpdatedAt": "2026-08-26T00:00:00Z"}},
    ],
)
def test_rank_context_normalizes_both_live_rpc_shapes(monkeypatch, publication_fields):
    source = {
        "setId": "set-a",
        "productFamilyRankings": {"families": {"etb": {"count": 27, "products": [{"setId": "set-a", "familyRank": 2}]}}},
        "target": {"evRepresentativeness": {"secret": True}, "openingOutcomeProfile": {"secret": True}, "setRipV1": {"secret": True}},
        **publication_fields,
    }
    monkeypatch.setattr(service, "get_pokemon_set_rip_global_context_payload", lambda *_args, **_kwargs: source)
    result = service.get_pokemon_set_rip_rank_context_payload("set-a")
    assert result["rankingCalculationRunId"] == "ranking-old"
    assert result["rankingUpdatedAt"] == "2026-08-26T00:00:00Z"
    assert result["productFamilyRankings"]["families"]["etb"]["products"][0]["familyRank"] == 2
    assert "target" not in result
    assert "evRepresentativeness" not in str(result)
    assert "openingOutcomeProfile" not in str(result)


def test_rank_context_fails_explicitly_when_publication_run_is_missing(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_pokemon_set_rip_global_context_payload",
        lambda *_args, **_kwargs: {"setId": "set-a", "productFamilyRankings": {"families": {}}, "meta": {}},
    )
    with pytest.raises(service.PokemonSetMarketError) as raised:
        service.get_pokemon_set_rip_rank_context_payload("set-a")
    assert raised.value.status_code == 503
    assert raised.value.code == "POKEMON_SET_RIP_RANK_CONTEXT_INCOMPLETE"


def test_simulation_enrichment_queries_exact_run_and_reuses_canonical_projector(monkeypatch):
    payload = {"contractVersion": "pokemon-set-rip-simulation-evidence-v1", "setId": "set-a", "calculationRunId": "run-current", "meta": {}}
    monkeypatch.setattr(service, "_read_set_rip_projection", lambda *_args, **_kwargs: payload)
    calls = {}

    class Query:
        def select(self, columns): calls["select"] = columns; return self
        def eq(self, key, value): calls.setdefault("eq", []).append((key, value)); return self
        def limit(self, value): return self
        def execute(self): return SimpleNamespace(data=[{"calculation_run_id": "run-current", "research_method_version": service.EV_REPRESENTATIVENESS_VERSION}])
    class Client:
        def table(self, name): calls["table"] = name; return Query()

    monkeypatch.setattr(service, "run_public_read_with_retry", lambda loader, **_kwargs: loader(Client()))
    monkeypatch.setattr(service, "project_opening_outcome_profile_v1", lambda row, expected_calculation_run_id: {"calculationRunId": expected_calculation_run_id, "buckets": []})
    result = service.get_pokemon_set_rip_simulation_evidence_snapshot_payload("set-a")
    assert calls["table"] == "ev_representativeness_run_summary"
    assert ("calculation_run_id", "run-current") in calls["eq"]
    assert "return_ratio_buckets_json" in calls["select"]
    assert "*" not in calls["select"]
    assert result["openingOutcomeProfile"]["calculationRunId"] == "run-current"


def test_ascended_current_run_projects_persisted_same_run_outcome_profile():
    run_id = "f2ed9183-1159-4782-b168-585a63397870"
    counts = [528894, 321752, 81345, 26174, 8732, 4456, 15919, 12728]
    bounds = [(0, .25), (.25, .5), (.5, .75), (.75, 1), (1, 1.5), (1.5, 2), (2, 5), (5, None)]
    sample_size = sum(counts)
    row = {
        "calculation_run_id": run_id,
        "research_method_version": service.EV_REPRESENTATIVENESS_VERSION,
        "market_date": "2026-08-28",
        "ev": 9.11176116,
        "p50": 3.33,
        "return_ratio_buckets_json": {
            "cost": 13.79,
            "sampleSize": sample_size,
            "buckets": [
                {
                    "ratioFloor": floor,
                    "ratioCeiling": ceiling,
                    "occurrenceCount": count,
                    "probability": count / sample_size,
                }
                for count, (floor, ceiling) in zip(counts, bounds)
            ],
        },
    }
    profile = service.project_opening_outcome_profile_v1(
        row, expected_calculation_run_id=run_id,
    )
    assert profile is not None
    assert profile["calculationRunId"] == run_id
    assert profile["expectedValue"] == pytest.approx(9.11176116)
    assert profile["medianValue"] == pytest.approx(3.33)
    under_half = next(
        item for item in profile["cumulativeProbabilities"] if item["key"] == "below_50"
    )
    assert under_half["probability"] == pytest.approx(0.850646)


def test_optional_research_failure_appends_warning_without_failing_simulation(monkeypatch):
    payload = {"contractVersion": "pokemon-set-rip-simulation-evidence-v1", "setId": "set-a", "calculationRunId": "run-current", "distributionBins": [{"x": 1}], "meta": {"warnings": ["existing warning"]}}
    monkeypatch.setattr(service, "_read_set_rip_projection", lambda *_args, **_kwargs: payload)
    monkeypatch.setattr(service, "run_public_read_with_retry", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("temporary")))
    result = service.get_pokemon_set_rip_simulation_evidence_snapshot_payload("set-a")
    assert result["distributionBins"] == [{"x": 1}]
    assert result["openingOutcomeProfile"] is None
    assert result["meta"]["warnings"][0] == "existing warning"
    assert len(result["meta"]["warnings"]) == 2
