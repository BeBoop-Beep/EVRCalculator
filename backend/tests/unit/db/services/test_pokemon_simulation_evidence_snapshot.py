from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.db.services import pokemon_public_snapshot_service as service
from backend.db.services.pokemon_set_market_service import PokemonSetMarketError


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows)


class _Client:
    def __init__(self, rows):
        self.rows = rows
        self.tables = []

    def table(self, name):
        self.tables.append(name)
        return _Query(self.rows.get(name, []))


def test_simulation_evidence_returns_allowlisted_exact_run_payload(monkeypatch):
    client = _Client({
        "pokemon_set_page_snapshot_latest": [{
            "updated_at": "2026-08-23T12:00:00+00:00",
            "payload_json": {
                "summary": {
                    "calculation_run_id": "run-1",
                    "market_date": "2026-08-21",
                    "mean_value": 4.25,
                    "private_internal_field": "must-not-leak",
                },
                "percentiles": [{"percentile": 50, "value": 2.0}],
                "distribution_bins": [{"minimum_value": 0, "maximum_value": 1}],
                "threshold_bins": [{"threshold": 5, "probability": 0.2}],
            },
        }],
    })
    monkeypatch.setattr(service, "service_read_client", client)
    monkeypatch.setattr(service, "_resolve_set_row", lambda _value: {"id": "set-1"})

    payload = service.get_pokemon_set_simulation_evidence_snapshot_payload("set-slug")

    assert payload["contractVersion"] == "pokemon-set-simulation-evidence-v1"
    assert payload["setId"] == "set-1"
    assert payload["calculationRunId"] == "run-1"
    assert payload["marketDate"] == "2026-08-21"
    assert payload["summary"] == {
        "calculationRunId": "run-1",
        "meanValue": 4.25,
    }
    assert payload["distributionBins"] == [{"minimum_value": 0, "maximum_value": 1}]
    assert client.tables == ["pokemon_set_page_snapshot_latest"]


def test_simulation_evidence_missing_snapshot_returns_standard_empty_payload(monkeypatch):
    client = _Client({"pokemon_set_page_snapshot_latest": []})
    monkeypatch.setattr(service, "service_read_client", client)
    monkeypatch.setattr(service, "_resolve_set_row", lambda _value: {"id": "set-1"})

    payload = service.get_pokemon_set_simulation_evidence_snapshot_payload("set-slug")

    assert payload["setId"] == "set-1"
    assert payload["summary"] == {}
    assert payload["percentiles"] == []
    assert payload["distributionBins"] == []
    assert payload["thresholdBins"] == []
    assert payload["meta"]["source"] == "empty_fallback_missing_pokemon_set_page_snapshot_latest"


def test_simulation_evidence_rejects_blank_identifier():
    with pytest.raises(PokemonSetMarketError) as excinfo:
        service.get_pokemon_set_simulation_evidence_snapshot_payload("  ")

    assert excinfo.value.status_code == 400
    assert excinfo.value.code == "POKEMON_SET_SIMULATION_EVIDENCE_ID_REQUIRED"


def test_api_route_is_wired_to_the_snapshot_service():
    api_source = (Path(__file__).resolve().parents[4] / "api" / "main.py").read_text(encoding="utf-8")
    assert '@app.get("/tcgs/pokemon/sets/{set_id}/simulation-evidence")' in api_source
    assert "get_pokemon_set_simulation_evidence_snapshot_payload(set_id=set_id)" in api_source
