import gc
import weakref
from types import SimpleNamespace

import numpy as np

from backend.db.services import pokemon_rip_stats_service as service


class _Result:
    def __init__(self, data): self.data = data


class _Query:
    def __init__(self, rows): self.rows = rows
    def select(self, *_a): return self
    def in_(self, *_a): return self
    def execute(self): return _Result(self.rows)


class _Client:
    def table(self, name):
        if name == "simulation_run_summary":
            return _Query([{"calculation_run_id": "run-a", "pack_cost": 5, "mean_value": 5},
                           {"calculation_run_id": "run-b", "pack_cost": 10, "mean_value": 10}])
        if name == "simulation_derived_metrics":
            return _Query([{"calculation_run_id": "run-a"}, {"calculation_run_id": "run-b"}])
        # Deliberately two DIFFERENT eras, so the partition is exercised rather
        # than trivially reproducing the global cohort.
        if name == "sets":
            return _Query([{"id": "a", "era_id": "era-1"}, {"id": "b", "era_id": "era-2"}])
        if name == "eras":
            return _Query([{"id": "era-1", "name": "Alpha"}, {"id": "era-2", "name": "Beta"}])
        raise AssertionError(name)


def test_service_processes_artifacts_sequentially_without_retaining_set_vectors(monkeypatch):
    statuses = [SimpleNamespace(set_id="a", canonical_key="a", calculation_run_id="run-a"),
                SimpleNamespace(set_id="b", canonical_key="b", calculation_run_id="run-b")]
    monkeypatch.setattr(service, "evaluate_opening_simulation_freshness", lambda *_a, **_k:
        SimpleNamespace(ok=True, statuses=statuses, eligible_count=2, error=None, failures=[]))
    monkeypatch.setattr(service, "resolve_eligible_sets", lambda _client: [
        {"id": "a", "release_date": "2020-01-01"}, {"id": "b", "release_date": "2020-01-01"}])
    monkeypatch.setattr(service, "load_pack_outcome_artifact_metadata", lambda _client, run_id:
        {"outcome_count": 4, "raw_sha256": ("a" if run_id == "run-a" else "b") * 64})
    alive = []; calls = []
    def load(_client, run_id):
        gc.collect()
        assert not any(reference() is not None for reference in alive), "previous decoded vector was retained"
        vector = np.array([0, 5, 10, 20], dtype=float) if run_id == "run-a" else np.array([0, 10, 20, 40], dtype=float)
        alive.append(weakref.ref(vector)); calls.append(run_id)
        return SimpleNamespace(metadata={"outcome_count": 4, "raw_sha256": ("a" if run_id == "run-a" else "b") * 64}, outcomes=vector)
    monkeypatch.setattr(service, "load_pack_outcome_artifact", load)
    built = service.build_pokemon_rip_stats_snapshot(_Client(), market_date="2026-08-17")
    # Global makes two streaming passes over both sets; each era then makes two
    # passes over only its own member. A set is never loaded for another era.
    assert calls == ["run-a", "run-b", "run-a", "run-b", "run-a", "run-a", "run-b", "run-b"]
    assert built["metrics"]["totalSourceOutcomeCount"] == 8

    eras = built["payload"]["openingEconomics"]["eras"]
    assert [era["eraName"] for era in eras] == ["Alpha", "Beta"]
    assert [era["setCount"] for era in eras] == [1, 1]
    # The era partition re-adds to the global cohort exactly.
    assert sum(era["setCount"] for era in eras) == built["metrics"]["setCount"]
    # No cross-era contamination: Alpha holds only run-a's $5 pack, Beta only run-b's $10.
    assert eras[0]["meanPackCost"] == 5.0
    assert eras[1]["meanPackCost"] == 10.0
