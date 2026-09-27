"""Real FastAPI acceptance tests for the canonical RIP Benchmark boundary."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient

from backend.api import main
from backend.benchmarking.registry_v1 import (
    BENCHMARK_KEY,
    V12_CALIBRATION_VERSION,
    contract_for_overall_model,
)
from backend.desirability.scoring_config import OVERALL_RIP_V12_VERSION


ENTITY_ID = "00000000-0000-0000-0000-000000000001"


def _install_auth(monkeypatch):
    plans = {"basic": None, "plus": "plus", "premium": "premium"}
    monkeypatch.setattr(
        main,
        "decode_token",
        lambda token: ({"id": f"user-{token}"}, None)
        if token in plans
        else (None, ({"message": "Not authenticated"}, 401)),
    )
    monkeypatch.setattr(
        main,
        "get_me",
        lambda token: ({"user": {"id": f"user-{token}", "index_plan": plans[token]}}, 200)
        if token in plans
        else ({"message": "Not authenticated"}, 401),
    )


class _Query:
    def __init__(self, owner):
        self.owner = owner

    def select(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=[{"model_version": self.owner.model_version}])


class _Client:
    def __init__(self, payload=None, *, model_version=OVERALL_RIP_V12_VERSION, error=None):
        self.model_version = model_version
        self.payload = payload or {"contract_version": "rip-benchmark-read-v1", "rows": []}
        self.error = error
        self.rpc_calls = []

    def table(self, _name):
        return _Query(self)

    def rpc(self, name, args):
        self.rpc_calls.append((name, args))
        return self

    def execute(self):
        if self.error:
            raise self.error
        return SimpleNamespace(data=deepcopy(self.payload))


def _headers(token):
    return {"authorization": f"Bearer {token}"}


def _entity(number=1, entity_type="set"):
    return {"entity_type": entity_type, "entity_id": str(UUID(int=number))}


def _client(monkeypatch, fake):
    calls = []
    monkeypatch.setattr(main, "_benchmark_client", lambda: calls.append("constructed") or fake)
    return TestClient(main.app, raise_server_exceptions=False), calls


def test_authentication_and_plus_gate_precede_client_construction(monkeypatch):
    _install_auth(monkeypatch)
    client, constructions = _client(monkeypatch, _Client())
    body = {"entities": [_entity()]}
    assert client.post("/tcgs/pokemon/rip-benchmark/current", json=body).status_code == 401
    assert client.post("/tcgs/pokemon/rip-benchmark/current", json=body, headers=_headers("basic")).status_code == 403
    assert constructions == []
    assert client.post("/tcgs/pokemon/rip-benchmark/current", json=body, headers=_headers("plus")).status_code == 200
    assert constructions == ["constructed"]


def test_public_set_headlines_preserve_public_access_and_project_only_safe_fields(monkeypatch):
    _install_auth(monkeypatch)
    private_row = {
        "entity_type": "set", "entity_id": ENTITY_ID, "metric_key": "overall",
        "benchmark_score": 6.3, "rank": 4, "cohort_size": 22,
        "benchmark_status": "available", "model_status": "available",
        "raw_model_value": 99, "benchmark_raw_value": 88, "raw_delta": 11,
        "source_fingerprint": "private",
        "expected_value_per_pack": 3.25,
    }
    fake = _Client({"contract_version": "rip-benchmark-read-v1", "status": "available",
                    "publication_id": None, "market_date": "2026-09-25",
                    "overall_model_version": OVERALL_RIP_V12_VERSION,
                    "rows": [private_row] + [
                        {"entity_type": "set", "entity_id": ENTITY_ID, "metric_key": metric,
                         "benchmark_score": None if metric == "financial" else 5.0,
                         "rank": None if metric == "financial" else rank, "cohort_size": 22,
                         "benchmark_status": "unavailable" if metric == "financial" else "available",
                         "model_status": "available"}
                        for rank, metric in enumerate(("financial", "chase", "collector"), 5)
                    ]})
    client, _ = _client(monkeypatch, fake)
    bodies = [({}, 200), ({"authorization": "Bearer basic"}, 200),
              ({"authorization": "Bearer plus"}, 200), ({"authorization": "Bearer premium"}, 200)]
    payloads = []
    for headers, status in bodies:
        response = client.post("/tcgs/pokemon/rip-benchmark/set-headlines", json={"set_ids": [ENTITY_ID]}, headers=headers)
        assert response.status_code == status
        payloads.append(response.json())
    assert payloads.count(payloads[0]) == 4
    row = payloads[0]["rows"][0]
    assert row["benchmark_score"] == 6.3 and row["rank"] == 4
    assert not ({"raw_model_value", "benchmark_raw_value", "raw_delta", "source_lineage", "source_fingerprint", "expected_value_per_pack"} & row.keys())
    assert payloads[0]["freshness"]["benchmarkMarketDate"] == "2026-09-25"
    assert {row["metric_key"] for row in payloads[0]["rows"]} == {"overall", "financial", "chase", "collector"}
    financial = next(row for row in payloads[0]["rows"] if row["metric_key"] == "financial")
    assert financial["benchmark_score"] is None and financial["rank"] is None
    full = client.post("/tcgs/pokemon/rip-benchmark/current", json={"entities": [_entity()]}, headers=_headers("plus")).json()
    assert [(r["benchmark_score"], r["rank"]) for r in payloads[0]["rows"]] == [(r["benchmark_score"], r["rank"]) for r in full["rows"]]


def test_public_set_headlines_is_set_only_bounded_and_model_authority_is_server_owned(monkeypatch):
    _install_auth(monkeypatch)
    fake = _Client()
    client, _ = _client(monkeypatch, fake)
    route = "/tcgs/pokemon/rip-benchmark/set-headlines"
    assert client.post(route, json={"set_ids": []}).status_code == 422
    assert client.post(route, json={"set_ids": [str(UUID(int=i)) for i in range(1, 12)]}).status_code == 422
    assert client.post(route, json={"entities": [_entity(entity_type="sealed_product")]}).status_code == 422
    assert client.post(route, json={"entities": [_entity(entity_type="era")]}).status_code == 422
    assert client.post(route, json={"set_ids": [ENTITY_ID], "benchmark_key": BENCHMARK_KEY}).status_code == 422


def test_public_shape_omits_versions_and_server_selects_registered_contract(monkeypatch):
    _install_auth(monkeypatch)
    fake = _Client({
        "contract_version": "rip-benchmark-read-v1", "status": "available",
        "market_date": "2026-09-25", "overall_model_version": OVERALL_RIP_V12_VERSION,
        "rows": [{"entity_type": "set", "entity_id": ENTITY_ID, "metric_key": "financial",
                  "benchmark_score": None, "rank": None}],
    })
    client, _ = _client(monkeypatch, fake)
    response = client.post("/tcgs/pokemon/rip-benchmark/current",
                           json={"entities": [_entity()]}, headers=_headers("plus"))
    assert response.status_code == 200
    assert fake.rpc_calls[0][1]["p_benchmark_key"] == BENCHMARK_KEY
    assert fake.rpc_calls[0][1]["p_calibration_version"] == V12_CALIBRATION_VERSION
    assert response.json()["rows"][0]["benchmark_score"] is None
    assert response.json()["freshness"] == {
        "benchmarkMarketDate": "2026-09-25", "modelSourceDate": "2026-09-25",
        "financialEvidenceDate": "2026-09-25", "activeModelVersion": OVERALL_RIP_V12_VERSION,
    }
    coupled = client.post("/tcgs/pokemon/rip-benchmark/current", json={
        "entities": [_entity()], "benchmark_key": BENCHMARK_KEY,
        "calibration_version": V12_CALIBRATION_VERSION,
    }, headers=_headers("plus"))
    assert coupled.status_code == 422


def test_unknown_future_model_fails_closed_without_rpc(monkeypatch):
    _install_auth(monkeypatch)
    fake = _Client(model_version="overall_rip_v14_hypothetical")
    client, _ = _client(monkeypatch, fake)
    response = client.post("/tcgs/pokemon/rip-benchmark/current",
                           json={"entities": [_entity()]}, headers=_headers("plus"))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "RIP_BENCHMARK_CONTRACT_UNAVAILABLE"
    assert fake.rpc_calls == []
    try:
        contract_for_overall_model("overall_rip_v14_hypothetical")
    except Exception as exc:
        assert "no canonical" in str(exc)
    else:
        raise AssertionError("unknown model silently inherited V12")


def test_request_bounds_and_entity_validation(monkeypatch):
    _install_auth(monkeypatch)
    fake = _Client()
    client, _ = _client(monkeypatch, fake)
    route = "/tcgs/pokemon/rip-benchmark/current"
    assert client.post(route, json={"entities": []}, headers=_headers("plus")).status_code == 422
    assert client.post(route, json={"entities": [_entity(entity_type="card")]}, headers=_headers("plus")).status_code == 422
    assert client.post(route, json={"entities": [_entity(i) for i in range(1, 11)]}, headers=_headers("plus")).status_code == 200
    assert client.post(route, json={"entities": [_entity(i) for i in range(1, 12)]}, headers=_headers("plus")).status_code == 422
    history = "/tcgs/pokemon/rip-benchmark/history"
    base = {"entities": [_entity()], "start_date": "2026-01-01", "end_date": "2026-01-01"}
    assert client.post(history, json={**base, "end_date": "2027-01-02"}, headers=_headers("plus")).status_code == 422
    assert client.post(history, json={**base, "limit": 1001}, headers=_headers("plus")).status_code == 422


def test_revision_conflict_is_409_and_not_retried(monkeypatch):
    _install_auth(monkeypatch)
    fake = _Client(error=RuntimeError("history publications changed; restart pagination"))
    client, _ = _client(monkeypatch, fake)
    response = client.post("/tcgs/pokemon/rip-benchmark/history", json={
        "entities": [_entity()], "start_date": "2026-09-15", "end_date": "2026-09-25",
    }, headers=_headers("plus"))
    assert response.status_code == 409
    assert len(fake.rpc_calls) == 1


def test_private_lineage_is_rejected_and_inherited_product_contract_is_preserved(monkeypatch):
    _install_auth(monkeypatch)
    private = _Client({"contract_version": "rip-benchmark-read-v1", "rows": [{"source_manifest": {"secret": 1}}]})
    client, _ = _client(monkeypatch, private)
    denied = client.post("/tcgs/pokemon/rip-benchmark/current",
                         json={"entities": [_entity()]}, headers=_headers("plus"))
    assert denied.status_code == 422
    inherited = _Client({
        "contract_version": "rip-benchmark-read-v1", "status": "available",
        "market_date": "2026-09-25", "overall_model_version": OVERALL_RIP_V12_VERSION,
        "rows": [{"entity_type": "sealed_product", "entity_id": ENTITY_ID,
                  "metric_key": "chase", "model_status": "inherited", "rank": None,
                  "inheritance_source_entity_type": "set", "inheritance_source_entity_id": str(UUID(int=2))}],
    })
    monkeypatch.setattr(main, "_benchmark_client", lambda: inherited)
    accepted = client.post("/tcgs/pokemon/rip-benchmark/current",
                           json={"entities": [_entity(entity_type="sealed_product")]}, headers=_headers("plus"))
    row = accepted.json()["rows"][0]
    assert row["model_status"] == "inherited" and row["rank"] is None
    assert row["inheritance_source_entity_type"] == "set"
