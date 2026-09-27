"""Offline candidate assembly and bounded private read adapter.

There is intentionally NO publisher call, schedule, API route or public feature
switch in this first backend bucket. Candidate payloads can be validated against
the deployed RPC on disposable Postgres without authorizing production writes.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence
import json

from backend.domain.pokemon.rip_benchmark_v1 import (
    BenchmarkError, ENTITY_TYPES, METRICS, day, fingerprint, identifier, number, wire,
)

PUBLISH_RPC = "publish_pokemon_rip_benchmark_v1"
CURRENT_RPC = "get_pokemon_rip_benchmark_current_v1"
HISTORY_RPC = "get_pokemon_rip_benchmark_history_v1"
HEADER_KEYS = frozenset({
    "id", "market_date", "benchmark_key", "calibration_version", "expected_entity_count",
    "expected_row_count", "cohort_fingerprint", "source_fingerprint", "overall_model_version",
    "financial_model_version", "chase_model_version", "collector_model_version",
    "collector_run_id", "collector_lineage_status", "active_overall_publication_id",
    "opening_economics_snapshot_id", "opening_economics_contract_version",
    "opening_economics_basis", "source_manifest",
})
SERVER_ROW_KEYS = frozenset({"publication_id", "market_date", "raw_delta", "score_delta"})
ADDITIONAL_REGISTERED_CALIBRATION_VERSIONS = frozenset({
    "rip_product_benchmark_v1_fin5_overall5_family_mean",
})


def candidate_request(header: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], *,
                      expected_previous_id: str | None = None) -> dict[str, Any]:
    """Prepare deterministic RPC arguments; never invoke the RPC."""
    if set(header) - HEADER_KEYS:
        raise BenchmarkError("unknown or server-owned header field")
    if not 4 <= len(rows) <= 5000:
        raise BenchmarkError("candidate requires 4..5000 metric rows")
    identifier(header.get("id")); identifier(header.get("active_overall_publication_id"))
    target_day = day(header.get("market_date"))
    if not header.get("benchmark_key") or not header.get("calibration_version"):
        raise BenchmarkError("explicit benchmark/calibration identity required")
    groups: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        typ, metric = row.get("entity_type"), row.get("metric_key")
        eid = identifier(row.get("entity_id"))
        if typ not in ENTITY_TYPES or metric not in METRICS or SERVER_ROW_KEYS & set(row):
            raise BenchmarkError("invalid identity or server-owned row fields")
        group = groups.setdefault((typ, eid), set())
        if metric in group:
            raise BenchmarkError("duplicate entity metric")
        group.add(metric)
        if row.get("model_status") != "unavailable":
            if row.get("source_model_version") != header.get(f"{metric}_model_version"):
                raise BenchmarkError("header/row source model mismatch")
            if day(row.get("source_market_date")) > target_day:
                raise BenchmarkError("future source")
        if row.get("benchmark_status") == "available":
            calibration = (row.get("source_lineage") or {}).get("benchmark_calibration") or {}
            if (calibration.get("version") != header.get("calibration_version")
                    and calibration.get("version") not in ADDITIONAL_REGISTERED_CALIBRATION_VERSIONS):
                raise BenchmarkError("row/header calibration version mismatch")
            raw, ref, score = (number(row.get(k)) for k in
                               ("raw_model_value", "benchmark_raw_value", "benchmark_score"))
            if not 0 <= score <= 10 or (raw == ref and score != 5) or (raw > ref and score <= 5) or (raw < ref and score >= 5):
                raise BenchmarkError("benchmark range/neutrality/direction violation")
    if any(metrics != set(METRICS) for metrics in groups.values()):
        raise BenchmarkError("all four metric rows required, including unavailable ones")
    if len(groups) > 1250:
        raise BenchmarkError("too many entities")
    if header.get("expected_entity_count") != len(groups) or header.get("expected_row_count") != len(rows):
        raise BenchmarkError("header/row cohort count mismatch")
    ordered = sorted((dict(row) for row in rows), key=lambda x: (x["entity_type"], x["entity_id"], x["metric_key"]))
    # Deliberately does not forge PostgreSQL's request_fingerprint. The RPC owns it.
    request = wire({"p_header": dict(header), "p_rows": ordered,
                    "p_expected_previous_id": identifier(expected_previous_id) if expected_previous_id else None})
    if len(json.dumps(request["p_rows"], ensure_ascii=False).encode("utf-8")) > 8 * 1024 * 1024:
        raise BenchmarkError("candidate exceeds 8 MiB row bound")
    return {"mode": "dry_run_only", "production_publish_enabled": False,
            "rpc": PUBLISH_RPC, "candidate_fingerprint": fingerprint(request), "arguments": request}


def entities_arg(entities: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    if not 1 <= len(entities) <= 10:
        raise BenchmarkError("read requires 1..10 entities")
    result = []
    for item in entities:
        if set(item) != {"entity_type", "entity_id"} or item.get("entity_type") not in ENTITY_TYPES:
            raise BenchmarkError("invalid entity selector")
        result.append({"entity_type": item["entity_type"], "entity_id": identifier(item["entity_id"])})
    if len({(r["entity_type"], r["entity_id"]) for r in result}) != len(result):
        raise BenchmarkError("duplicate requested entity")
    return sorted(result, key=lambda r: (r["entity_type"], r["entity_id"]))


class PrivateBenchmarkReader:
    """Authorization precedes client creation/DB access. Not an exposed API route.

    The injected client factory MUST configure the transport timeout supplied in
    seconds. One request makes ONE bounded RPC; there are no hidden retries,
    per-entity queries, stale fallbacks or unbounded ALL loops.
    """
    def __init__(self, *, require_access: Callable[[], None],
                 client_factory: Callable[[float], Any], timeout_seconds: float = 10.0):
        if not callable(require_access) or not callable(client_factory):
            raise BenchmarkError("server access check and bounded client factory required")
        if not 0 < number(timeout_seconds) <= 30:
            raise BenchmarkError("read timeout must be >0 and <=30 seconds")
        self.require_access, self.client_factory = require_access, client_factory
        self.timeout = float(timeout_seconds)

    def _read(self, rpc: str, args: dict[str, Any]) -> dict[str, Any]:
        if self.require_access() is False:
            raise PermissionError("benchmark analytics access denied")
        response = self.client_factory(self.timeout).rpc(rpc, args).execute()
        data = getattr(response, "data", None)
        if not isinstance(data, Mapping) or data.get("contract_version") != "rip-benchmark-read-v1":
            raise BenchmarkError("invalid benchmark read contract")
        # DB read contract has already excluded private lineage. Defense in depth:
        # fail closed on unexpected private payloads instead of silently forwarding.
        private = {"source_lineage", "source_manifest", "active_release_lineage", "payload_json", "outcomes"}
        def check(value: Any) -> None:
            if isinstance(value, Mapping):
                if private & set(value):
                    raise BenchmarkError("private source material in compact read")
                for child in value.values(): check(child)
            elif isinstance(value, list):
                for child in value: check(child)
        check(data)
        rows = data.get("rows")
        maximum = len(args["p_entities"]) * 4 if rpc == CURRENT_RPC else args["p_limit"]
        if not isinstance(rows, list) or len(rows) > maximum:
            raise BenchmarkError("compact response exceeded requested row bound")
        return dict(data)

    @staticmethod
    def _keys(benchmark_key: str, calibration_version: str) -> dict[str, str]:
        if (not isinstance(benchmark_key, str) or not 1 <= len(benchmark_key) <= 100 or
            not isinstance(calibration_version, str) or not 1 <= len(calibration_version) <= 160):
            raise BenchmarkError("explicit bounded benchmark/calibration required")
        return {"p_benchmark_key": benchmark_key, "p_calibration_version": calibration_version}

    def current(self, entities: Sequence[Mapping[str, Any]], *, benchmark_key: str,
                calibration_version: str) -> dict[str, Any]:
        args = {**self._keys(benchmark_key, calibration_version), "p_entities": entities_arg(entities)}
        return self._read(CURRENT_RPC, args)

    def history_page(self, entities: Sequence[Mapping[str, Any]], *, start_date: str,
                     end_date: str, benchmark_key: str, calibration_version: str,
                     limit: int = 500, after: Mapping[str, Any] | None = None) -> dict[str, Any]:
        start, end = day(start_date), day(end_date)
        if not 0 <= (end - start).days <= 365 or type(limit) is not int or not 1 <= limit <= 1000:
            raise BenchmarkError("history requires <=366 inclusive days and <=1000 rows")
        if after is not None and (not isinstance(after, Mapping) or len(json.dumps(after).encode()) > 1024):
            raise BenchmarkError("invalid or oversized cursor")
        args = {**self._keys(benchmark_key, calibration_version), "p_entities": entities_arg(entities),
                "p_start_date": start.isoformat(), "p_end_date": end.isoformat(),
                "p_limit": limit, "p_after": dict(after) if after is not None else None}
        # Revision conflicts propagate; never restart midway and concatenate generations.
        return self._read(HISTORY_RPC, args)
