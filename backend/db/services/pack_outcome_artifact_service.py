from __future__ import annotations

import hashlib
import zlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np


TABLE = "simulation_pack_outcome_artifacts"
FORMAT_VERSION = 1
NUMERIC_DTYPE = "float64"
BYTE_ORDER = "little"
COMPRESSION_FORMAT = "zlib"


class PackOutcomeArtifactError(RuntimeError):
    pass


class PackOutcomeArtifactUnavailable(PackOutcomeArtifactError):
    pass


class PackOutcomeArtifactCorrupt(PackOutcomeArtifactError):
    pass


@dataclass(frozen=True)
class EncodedPackOutcomeArtifact:
    outcome_count: int
    raw_size_bytes: int
    compressed_size_bytes: int
    raw_sha256: str
    payload: bytes


@dataclass(frozen=True)
class LoadedPackOutcomeArtifact:
    metadata: Mapping[str, Any]
    outcomes: np.ndarray


def encode_pack_outcomes(values: Sequence[float]) -> EncodedPackOutcomeArtifact:
    vector = np.asarray(values, dtype="<f8")
    if vector.ndim != 1 or vector.size == 0:
        raise ValueError("pack outcome vector must be a non-empty one-dimensional sequence")
    if not np.isfinite(vector).all():
        raise ValueError("pack outcome vector contains a non-finite value")
    raw = vector.tobytes(order="C")
    compressed = zlib.compress(raw, level=9)
    return EncodedPackOutcomeArtifact(
        outcome_count=int(vector.size),
        raw_size_bytes=len(raw),
        compressed_size_bytes=len(compressed),
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        payload=compressed,
    )


def _decode_bytea(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str) and value.startswith("\\x"):
        try:
            return bytes.fromhex(value[2:])
        except ValueError as exc:
            raise PackOutcomeArtifactCorrupt("artifact payload is not valid hex bytea") from exc
    raise PackOutcomeArtifactCorrupt("artifact payload has an unsupported representation")


def decode_pack_outcomes(row: Mapping[str, Any]) -> np.ndarray:
    expected = {
        "format_version": FORMAT_VERSION,
        "numeric_dtype": NUMERIC_DTYPE,
        "byte_order": BYTE_ORDER,
        "compression_format": COMPRESSION_FORMAT,
    }
    for field, value in expected.items():
        if row.get(field) != value:
            raise PackOutcomeArtifactCorrupt(f"unsupported artifact {field}: {row.get(field)!r}")
    payload = _decode_bytea(row.get("payload"))
    if len(payload) != int(row.get("compressed_size_bytes") or -1):
        raise PackOutcomeArtifactCorrupt("compressed size mismatch")
    try:
        raw = zlib.decompress(payload)
    except zlib.error as exc:
        raise PackOutcomeArtifactCorrupt("artifact decompression failed") from exc
    if len(raw) != int(row.get("raw_size_bytes") or -1):
        raise PackOutcomeArtifactCorrupt("raw size mismatch")
    if hashlib.sha256(raw).hexdigest() != row.get("raw_sha256"):
        raise PackOutcomeArtifactCorrupt("artifact checksum mismatch")
    count = int(row.get("outcome_count") or -1)
    if len(raw) != count * 8:
        raise PackOutcomeArtifactCorrupt("outcome count mismatch")
    vector = np.frombuffer(raw, dtype="<f8").copy()
    vector.flags.writeable = False
    return vector


def persist_pack_outcomes(client: Any, calculation_run_id: Any, values: Sequence[float]) -> dict[str, Any]:
    encoded = encode_pack_outcomes(values)
    run_id = str(calculation_run_id)
    existing = client.table(TABLE).select("*").eq("calculation_run_id", run_id).limit(1).execute()
    rows = existing.data if existing and existing.data else []
    if rows:
        row = rows[0]
        if row.get("raw_sha256") != encoded.raw_sha256 or int(row.get("outcome_count") or -1) != encoded.outcome_count:
            raise PackOutcomeArtifactCorrupt("calculation run already has a different outcome artifact")
        decode_pack_outcomes(row)
        return {"status": "matched", "outcome_count": encoded.outcome_count, "raw_sha256": encoded.raw_sha256,
                "raw_size_bytes": encoded.raw_size_bytes, "compressed_size_bytes": encoded.compressed_size_bytes}
    payload = {
        "calculation_run_id": run_id, "format_version": FORMAT_VERSION,
        "numeric_dtype": NUMERIC_DTYPE, "byte_order": BYTE_ORDER,
        "compression_format": COMPRESSION_FORMAT, "outcome_count": encoded.outcome_count,
        "raw_size_bytes": encoded.raw_size_bytes, "compressed_size_bytes": encoded.compressed_size_bytes,
        "raw_sha256": encoded.raw_sha256, "payload": "\\x" + encoded.payload.hex(),
    }
    response = client.table(TABLE).insert(payload).execute()
    if not response or not response.data:
        raise PackOutcomeArtifactError("artifact insert returned no row")
    return {"status": "created", "outcome_count": encoded.outcome_count, "raw_sha256": encoded.raw_sha256,
            "raw_size_bytes": encoded.raw_size_bytes, "compressed_size_bytes": encoded.compressed_size_bytes}


def load_pack_outcomes(client: Any, calculation_run_id: Any) -> np.ndarray:
    return load_pack_outcome_artifact(client, calculation_run_id).outcomes


def load_pack_outcome_artifact(client: Any, calculation_run_id: Any) -> LoadedPackOutcomeArtifact:
    """Load one artifact and return validated provenance plus a read-only vector."""
    response = client.table(TABLE).select("*").eq("calculation_run_id", str(calculation_run_id)).limit(1).execute()
    rows = response.data if response and response.data else []
    if not rows:
        raise PackOutcomeArtifactUnavailable(
            f"calculation run {calculation_run_id} has no exact pack-outcome artifact; replay unavailable"
        )
    row = dict(rows[0])
    vector = decode_pack_outcomes(row)
    metadata = {key: row.get(key) for key in (
        "calculation_run_id", "format_version", "numeric_dtype", "byte_order", "compression_format",
        "outcome_count", "raw_size_bytes", "compressed_size_bytes", "raw_sha256", "created_at",
    )}
    return LoadedPackOutcomeArtifact(metadata=metadata, outcomes=vector)
