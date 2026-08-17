from __future__ import annotations

import numpy as np

from backend.db.services.pack_outcome_artifact_service import (
    BYTE_ORDER, COMPRESSION_FORMAT, FORMAT_VERSION, NUMERIC_DTYPE, encode_pack_outcomes,
)
from backend.db.services.sealed_product_replay_service import replay_sealed_products_for_run


class Response:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, rows): self.rows = rows
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def limit(self, *_args): return self
    def execute(self): return Response(self.rows)


class Client:
    def __init__(self, tables): self.tables = tables
    def table(self, name): return Query(self.tables.get(name, []))


def _artifact_row(values):
    item = encode_pack_outcomes(values)
    return {"format_version": FORMAT_VERSION, "numeric_dtype": NUMERIC_DTYPE,
            "byte_order": BYTE_ORDER, "compression_format": COMPRESSION_FORMAT,
            "outcome_count": item.outcome_count, "raw_size_bytes": item.raw_size_bytes,
            "compressed_size_bytes": item.compressed_size_bytes, "raw_sha256": item.raw_sha256,
            "payload": "\\x" + item.payload.hex()}


def test_legacy_run_is_explicitly_unavailable_without_bin_fallback():
    client = Client({"calculation_runs": [{"id": "run", "target_type": "set",
                     "target_id": "set", "calculation_config_id": "cfg"}]})
    result = replay_sealed_products_for_run(client, "run")
    assert result["status"] == "unavailable"
    assert result["reason"] == "exact_pack_outcome_artifact_unavailable"


def test_replay_passes_bit_exact_vector_and_original_run_identity_to_scorer():
    original = np.array([0.0, -0.0, np.nextafter(7.0, 8.0)], dtype=np.float64)
    client = Client({
        "calculation_runs": [{"id": "run", "target_type": "set", "target_id": "set",
                              "calculation_config_id": "cfg"}],
        "simulation_pack_outcome_artifacts": [_artifact_row(original)],
        "sets": [{"id": "set", "canonical_key": "exampleSet"}],
        "calculation_configs": [{"config_hash": "fingerprint"}],
    })
    captured = {}
    def scorer(**kwargs):
        captured.update(kwargs)
        return {"status": "completed"}
    result = replay_sealed_products_for_run(client, "run", scorer=scorer)
    assert result == {"status": "completed"}
    assert np.array_equal(captured["sim_results"]["values"].view(np.uint64), original.view(np.uint64))
    assert captured["calculation_run_id"] == "run"
    assert captured["run_fingerprint"] == "fingerprint"


def test_artifact_replay_scoring_matches_in_memory_scoring():
    original = np.array([1.25, 2.5, 9.75], dtype=np.float64)
    client = Client({
        "calculation_runs": [{"id": "run", "target_type": "set", "target_id": "set",
                              "calculation_config_id": "cfg"}],
        "simulation_pack_outcome_artifacts": [_artifact_row(original)],
        "sets": [{"id": "set", "canonical_key": "exampleSet"}],
        "calculation_configs": [{"config_hash": "fingerprint"}],
    })
    def scorer(**kwargs):
        values = kwargs["sim_results"]["values"]
        return {"mean": float(np.mean(values)), "median": float(np.median(values)),
                "run": kwargs["calculation_run_id"]}
    in_memory = scorer(sim_results={"values": original}, calculation_run_id="run")
    replayed = replay_sealed_products_for_run(client, "run", scorer=scorer)
    assert replayed == in_memory
