from __future__ import annotations

import numpy as np
import pytest
from postgrest.exceptions import APIError

from backend.db.services.pack_outcome_artifact_service import (
    BYTE_ORDER, COMPRESSION_FORMAT, FORMAT_VERSION, NUMERIC_DTYPE,
    LoadedPackOutcomeArtifact, PackOutcomeArtifactCorrupt,
    PackOutcomeArtifactUnavailable, decode_pack_outcomes, encode_pack_outcomes,
    load_pack_outcome_artifact, persist_pack_outcomes,
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


def _statement_timeout_error():
    return APIError(
        {
            "message": "canceling statement due to statement timeout",
            "code": "57014",
            "hint": None,
            "details": None,
        }
    )


def _permanent_error():
    return APIError(
        {
            "message": "column \"bogus\" does not exist",
            "code": "42703",
            "hint": None,
            "details": None,
        }
    )


class _FlakyQuery:
    def __init__(self, client): self.client = client
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def limit(self, *_args): return self

    def execute(self):
        self.client.attempts += 1
        if self.client.failures:
            failure = self.client.failures.pop(0)
            raise failure
        return _Response(self.client.rows)


class _FlakyClient:
    def __init__(self, rows, failures):
        self.rows = rows
        self.failures = list(failures)
        self.attempts = 0

    def table(self, _name):
        return _FlakyQuery(self)


def _artifact_row(values, calculation_run_id="run-1"):
    row = _row(values)
    row["calculation_run_id"] = calculation_run_id
    row["created_at"] = "2026-09-22T00:00:00Z"
    return row


def test_load_artifact_succeeds_on_first_attempt_with_unchanged_semantics():
    client = _FlakyClient([_artifact_row([1.0, 2.0, 3.0])], failures=[])

    loaded = load_pack_outcome_artifact(client, "run-1")

    assert isinstance(loaded, LoadedPackOutcomeArtifact)
    assert np.array_equal(loaded.outcomes, np.array([1.0, 2.0, 3.0]))
    assert loaded.metadata["calculation_run_id"] == "run-1"
    assert client.attempts == 1


def test_load_artifact_retries_once_on_statement_timeout_then_succeeds(monkeypatch):
    # `run_batch_read_with_retry` binds `sleep=time.sleep` as a default
    # argument at import time, so patching the module's `time` attribute
    # after the fact does not intercept it; patch the function's own default
    # instead so the retry sleep is observed without a real delay.
    import backend.db.services.public_read_retry as retry_module

    sleeps = []
    monkeypatch.setitem(retry_module.run_batch_read_with_retry.__kwdefaults__, "sleep", sleeps.append)
    monkeypatch.setitem(
        retry_module.run_batch_read_with_retry.__kwdefaults__, "jitter", lambda _a, _b: 0.0
    )

    client = _FlakyClient(
        [_artifact_row([4.0, 5.0])],
        failures=[_statement_timeout_error()],
    )

    loaded = load_pack_outcome_artifact(client, "run-2")

    assert np.array_equal(loaded.outcomes, np.array([4.0, 5.0]))
    assert client.attempts == 2
    assert len(sleeps) == 1


def test_load_artifact_exhausts_retry_budget_on_repeated_statement_timeout(monkeypatch):
    import backend.db.services.public_read_retry as retry_module

    monkeypatch.setitem(retry_module.run_batch_read_with_retry.__kwdefaults__, "sleep", lambda _s: None)
    monkeypatch.setitem(
        retry_module.run_batch_read_with_retry.__kwdefaults__, "jitter", lambda _a, _b: 0.0
    )

    client = _FlakyClient(
        [_artifact_row([1.0])],
        failures=[_statement_timeout_error() for _ in range(4)],
    )

    with pytest.raises(RuntimeError) as excinfo:
        load_pack_outcome_artifact(client, "run-3")

    message = str(excinfo.value)
    assert "run-3" in message
    assert "57014" in message or "statement timeout" in message.lower()
    assert "4" in message  # attempt count is reported
    assert client.attempts == 4  # bounded, not infinite


def test_load_artifact_does_not_retry_non_transient_error():
    client = _FlakyClient([_artifact_row([1.0])], failures=[_permanent_error()])

    with pytest.raises(APIError):
        load_pack_outcome_artifact(client, "run-4")

    assert client.attempts == 1  # no retry for a non-transient error


def test_load_artifact_missing_row_raises_unavailable_unchanged():
    client = _FlakyClient([], failures=[])

    with pytest.raises(PackOutcomeArtifactUnavailable):
        load_pack_outcome_artifact(client, "run-5")

    assert client.attempts == 1
