from __future__ import annotations

import numpy as np
import pytest

from backend.db.services.pack_outcome_artifact_service import (
    BYTE_ORDER, COMPRESSION_FORMAT, FORMAT_VERSION, NUMERIC_DTYPE,
    PackOutcomeArtifactCorrupt, decode_pack_outcomes, encode_pack_outcomes,
    persist_pack_outcomes,
)


def _row(values):
    artifact = encode_pack_outcomes(values)
    return {
        "format_version": FORMAT_VERSION, "numeric_dtype": NUMERIC_DTYPE,
        "byte_order": BYTE_ORDER, "compression_format": COMPRESSION_FORMAT,
        "outcome_count": artifact.outcome_count, "raw_size_bytes": artifact.raw_size_bytes,
        "compressed_size_bytes": artifact.compressed_size_bytes,
        "raw_sha256": artifact.raw_sha256, "payload": "\\x" + artifact.payload.hex(),
    }


def test_float64_round_trip_is_bit_exact_and_read_only():
    original = np.array([0.0, -0.0, 1.25, np.nextafter(2.0, 3.0)], dtype=np.float64)
    loaded = decode_pack_outcomes(_row(original))
    assert loaded.dtype == np.dtype("float64")
    assert np.array_equal(original.view(np.uint64), loaded.view(np.uint64))
    assert not loaded.flags.writeable


@pytest.mark.parametrize("field,value", [("format_version", 2), ("numeric_dtype", "float32"),
                                          ("byte_order", "big"), ("compression_format", "gzip")])
def test_rejects_unsupported_contract(field, value):
    row = _row([1.0])
    row[field] = value
    with pytest.raises(PackOutcomeArtifactCorrupt):
        decode_pack_outcomes(row)


def test_rejects_checksum_corruption():
    row = _row([1.0, 2.0])
    row["raw_sha256"] = "0" * 64
    with pytest.raises(PackOutcomeArtifactCorrupt, match="checksum"):
        decode_pack_outcomes(row)


def test_rejects_wrong_outcome_count():
    row = _row([1.0, 2.0])
    row["outcome_count"] = 3
    with pytest.raises(PackOutcomeArtifactCorrupt, match="outcome count"):
        decode_pack_outcomes(row)


def test_rejects_truncated_artifact():
    row = _row([1.0, 2.0])
    payload = bytes.fromhex(row["payload"][2:])[:-1]
    row["payload"] = "\\x" + payload.hex()
    row["compressed_size_bytes"] = len(payload)
    with pytest.raises(PackOutcomeArtifactCorrupt, match="decompression"):
        decode_pack_outcomes(row)


class _Response:
    def __init__(self, data): self.data = data


class _Query:
    def __init__(self, client): self.client = client
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def limit(self, *_args): return self
    def execute(self): return _Response(self.client.rows)
    def insert(self, payload):
        self.client.insert_count += 1
        self.client.rows = [payload]
        return self


class _Client:
    def __init__(self): self.rows, self.insert_count = [], 0
    def table(self, _name): return _Query(self)


def test_persistence_is_idempotent_for_the_same_run_and_vector():
    client = _Client()
    first = persist_pack_outcomes(client, "run", [1.0, 2.0])
    second = persist_pack_outcomes(client, "run", [1.0, 2.0])
    assert first["status"] == "created"
    assert second["status"] == "matched"
    assert client.insert_count == 1
