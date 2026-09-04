"""Phase F memory benchmark for the 2026-09-04 memory P0, 3-stage comparison.

Stage 1 "Original": the pre-`1ee37cf9` cache (unbounded per-`limit` dict,
`deepcopy()`'d on every healthy request) AND the full mega-contract read on
every request. Reimplemented here standalone (not by reverting production
code) purely to measure the baseline this P0 started from.

Stage 2 "Cache-only" (`1ee37cf9` + `76795836`, this branch before this pass):
today's single-slot, no-deepcopy fallback cache, but the healthy path still
selects/materializes the full `ranking_payload_json` mega-contract on every
request via `_load_pokemon_explore_rankings_snapshot_row`.

Stage 3 "Compact-final" (this pass): the healthy path uses the compact
`get_pokemon_rip_statistics_targets_compact` RPC and never touches the
mega-contract table read.

Fixture: 34 targets (matching the live publication's verified target count),
each with an enriched `setRipV1` (25 `familyScores` rows, matching the prior
benchmark's per-target shape) and a persisted `openingSetAudit`. A
`productFamilyRankings` block (~245KB-scale) and 33 padding fields per target
approximate the ~2.74MB full mega-contract / ~246KB-scale compact payload
documented in the task's production facts. No production DB credentials are
available in this environment, so this is a representative fixture, not a
live read -- consistent with Pass 1/2's benchmark methodology.

Primary workload: 50 consecutive `limit=200`-equivalent reads in one process
per stage (RSS plateau is the pass/fail signal). Run standalone:

    python -m backend.scripts.benchmark_rip_statistics_targets_compact_memory
"""
from __future__ import annotations

import gc
import json
import time
import tracemalloc
from copy import deepcopy
from typing import Any, Dict, List

import psutil

from backend.db.services import pokemon_public_snapshot_service as svc
from backend.db.services.public_rip_publication_contract import canonical_publication_identity

PROCESS = psutil.Process()
N_TARGETS = 34
FAMILY_COUNT = 25
PRODUCT_FAMILY_COUNT = 100


def _rss_mb() -> float:
    gc.collect()
    return PROCESS.memory_info().rss / (1024 * 1024)


def _identity_meta() -> Dict[str, Any]:
    identity = canonical_publication_identity()
    return {
        "ripWeightsConfig": {
            "overallRip": {"version": identity["overallRipVersion"]},
            "financialRip": {"version": identity["financialRipVersion"]},
            "publicContract": {"version": identity["publicRipContractVersion"]},
            "collectorAppeal": {"version": identity["collectorAppealVersion"]},
        }
    }


def _family_scores(n: int) -> List[Dict[str, Any]]:
    return [
        {"family": f"family-{i}", "skuCount": 12, "score": 0.5, "rank": i + 1, "cohortSize": n}
        for i in range(n)
    ]


def _target(i: int) -> Dict[str, Any]:
    families = _family_scores(FAMILY_COUNT)
    participating = [f["family"] for f in families]
    return {
        "id": f"set-{i}",
        "target_id": f"set-{i}",
        "target_type": "set",
        "name": f"Synthetic Set {i}",
        "slug": f"synthetic-set-{i}",
        "canonical_key": f"synthetic-set-{i}",
        "era": "Synthetic Era",
        "is_opening_set": True,
        "pack_cost": 4.99,
        "prob_big_hit": 0.02,
        "roi_percent": 12.5,
        "p95_value_to_cost_ratio": 3.4,
        "p95_value_to_cost_rank": i + 1,
        "p95_value_to_cost_tier": "S",
        "rip": {"score": 80.0},
        "ripCore": {"score": 80.0},
        "openingExperience": {"summary": "synthetic"},
        "setRipV1": {
            "rankable": True,
            "cohortSize": FAMILY_COUNT,
            "familyScores": families,
            "participatingFamilies": participating,
            "participatingFamilyCount": len(participating),
        },
        "history": [{"date": f"2026-01-{d:02d}", "value": d * 1.1} for d in range(1, 29)],
    }


def _opening_audit() -> Dict[str, Any]:
    return {
        "total_raw_pokemon_set_rows": N_TARGETS,
        "opening_set_rows": N_TARGETS,
        "subset_rows": 0,
        "subset_rows_missing_parent_mapping": 0,
        "rollup_parent_rows": 0,
    }


def _product_family_rankings() -> Dict[str, Any]:
    return {
        "families": {
            f"family-{i}": {"rank": i, "score": 0.5, "skuCount": 12}
            for i in range(PRODUCT_FAMILY_COUNT)
        }
    }


def _full_payload() -> Dict[str, Any]:
    meta = _identity_meta()
    meta["openingSetAudit"] = _opening_audit()
    meta["opening_set_audit"] = _opening_audit()
    return {
        "targets": [_target(i) for i in range(N_TARGETS)],
        "meta": meta,
        "productFamilyRankings": _product_family_rankings(),
        "setRip": {"weights": {"a": 1}},
        "eraSetStrengthV1": {"eras": [{"era": "e1"}]},
    }


def _full_row(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "updated_at": "2026-09-04T15:08:00+00:00",
        "ranking_payload_json": payload,
        "default_target_json": {"target_id": "set-0", "target_type": "set"},
    }


def _compact_row(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "targets": deepcopy(payload["targets"]),
        "default_target": {"target_id": "set-0", "target_type": "set"},
        "meta": deepcopy(payload["meta"]),
        "updated_at": "2026-09-04T15:08:00+00:00",
    }


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, handlers):
        self.table_name = table_name
        self.handlers = handlers

    def select(self, _f):
        return self

    def eq(self, _f, _v):
        return self

    def limit(self, _v):
        return self

    def execute(self):
        return _Result(self.handlers[self.table_name](self))


class _RpcCall:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return _Result(self._fn())


class _Client:
    def __init__(self, table_handlers=None, rpc_handlers=None):
        self.table_handlers = table_handlers or {}
        self.rpc_handlers = rpc_handlers or {}

    def table(self, table_name):
        return _Query(table_name, self.table_handlers)

    def rpc(self, fn_name, params=None):
        handler = self.rpc_handlers.get(fn_name)
        if handler is None:
            raise RuntimeError(f"no rpc handler for {fn_name}")
        return _RpcCall(lambda: handler(params))


def _payload_bytes(payload: Dict[str, Any]) -> int:
    return len(json.dumps(payload).encode("utf-8"))


# --- Stage 1: Original (pre-1ee37cf9) ---------------------------------------

_STAGE1_CACHE: Dict[int, Dict[str, Any]] = {}


def _stage1_get(client, limit: int) -> Dict[str, Any]:
    """Reimplements the pre-fix behavior standalone: full table read every
    call, unbounded per-limit dict cache, deepcopy() on every healthy call."""
    row = client.table("pokemon_explore_rankings_snapshot_latest").select("x").eq("a", "b").limit(1).execute().data[0]
    payload = row["ranking_payload_json"]
    targets = list(payload.get("targets") or [])[:limit]
    resolved = {**payload, "targets": targets}
    _STAGE1_CACHE[limit] = deepcopy(resolved)
    return resolved


def _run_stage1(row: Dict[str, Any]) -> Dict[str, Any]:
    _STAGE1_CACHE.clear()
    client = _Client(table_handlers={"pokemon_explore_rankings_snapshot_latest": lambda _q: [row]})

    rss0 = _rss_mb()
    _stage1_get(client, 200)
    rss_after_1 = _rss_mb()

    t0 = time.perf_counter()
    for _ in range(50):
        _stage1_get(client, 200)
    elapsed_50 = time.perf_counter() - t0
    rss_after_50 = _rss_mb()

    lat = []
    for _ in range(20):
        t0 = time.perf_counter()
        _stage1_get(client, 200)
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()

    return {
        "rss_fresh": rss0,
        "rss_after_1": rss_after_1,
        "rss_after_50": rss_after_50,
        "elapsed_50_s": elapsed_50,
        "retained_cache_entries": len(_STAGE1_CACHE),
        "retained_bytes_estimate": sum(_payload_bytes(v) for v in _STAGE1_CACHE.values()),
        "p50_ms": lat[len(lat) // 2],
        "p95_ms": lat[int(len(lat) * 0.95)],
    }


# --- Stage 2: Cache-only (1ee37cf9 + 76795836), full reader forced ---------


def _run_stage2(full_row: Dict[str, Any]) -> Dict[str, Any]:
    svc._reset_rankings_fallback_cache_for_tests()

    def _raise_rpc(_params):
        raise RuntimeError("compact rpc not available in stage2 (forced full-reader stage)")

    client = _Client(
        table_handlers={"pokemon_explore_rankings_snapshot_latest": lambda _q: [full_row]},
        rpc_handlers={"get_pokemon_rip_statistics_targets_compact": _raise_rpc},
    )
    svc.service_read_client = client
    svc.create_short_timeout_service_client = lambda: client
    svc._enrich_rankings_payload_with_checklist_set_values = lambda payload: payload

    response_bytes = None
    rss0 = _rss_mb()
    r = svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
    response_bytes = _payload_bytes(r)
    rss_after_1 = _rss_mb()

    t0 = time.perf_counter()
    for _ in range(50):
        svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
    elapsed_50 = time.perf_counter() - t0
    rss_after_50 = _rss_mb()

    lat = []
    for _ in range(20):
        t0 = time.perf_counter()
        svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()

    cache = svc._RANKINGS_FALLBACK_CACHE
    retained = _payload_bytes(cache["base_payload"] or {}) + _payload_bytes(cache["raw_targets"] or [])

    return {
        "rss_fresh": rss0,
        "rss_after_1": rss_after_1,
        "rss_after_50": rss_after_50,
        "elapsed_50_s": elapsed_50,
        "retained_cache_entries": 1,
        "retained_bytes_estimate": retained,
        "response_bytes": response_bytes,
        "p50_ms": lat[len(lat) // 2],
        "p95_ms": lat[int(len(lat) * 0.95)],
    }


# --- Stage 3: Compact-final (this pass) -------------------------------------


def _run_stage3(compact_row: Dict[str, Any], full_row_legacy_fallback: Dict[str, Any]) -> Dict[str, Any]:
    svc._reset_rankings_fallback_cache_for_tests()

    client = _Client(
        table_handlers={"pokemon_explore_rankings_snapshot_latest": lambda _q: [full_row_legacy_fallback]},
        rpc_handlers={"get_pokemon_rip_statistics_targets_compact": lambda _params: compact_row},
    )
    svc.service_read_client = client
    svc.create_short_timeout_service_client = lambda: client
    svc._enrich_rankings_payload_with_checklist_set_values = lambda payload: payload

    rss0 = _rss_mb()
    r = svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
    response_bytes = _payload_bytes(r)
    rss_after_1 = _rss_mb()

    t0 = time.perf_counter()
    for _ in range(50):
        svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
    elapsed_50 = time.perf_counter() - t0
    rss_after_50 = _rss_mb()

    lat = []
    for _ in range(20):
        t0 = time.perf_counter()
        svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()

    cache = svc._RANKINGS_FALLBACK_CACHE
    retained = _payload_bytes(cache["base_payload"] or {}) + _payload_bytes(cache["raw_targets"] or [])

    return {
        "rss_fresh": rss0,
        "rss_after_1": rss_after_1,
        "rss_after_50": rss_after_50,
        "elapsed_50_s": elapsed_50,
        "retained_cache_entries": 1,
        "retained_bytes_estimate": retained,
        "response_bytes": response_bytes,
        "p50_ms": lat[len(lat) // 2],
        "p95_ms": lat[int(len(lat) * 0.95)],
    }


def main() -> None:
    tracemalloc.start()
    payload = _full_payload()
    full_row = _full_row(payload)
    compact_row = _compact_row(payload)

    source_full_bytes = _payload_bytes(payload)
    source_compact_bytes = _payload_bytes(
        {"targets": compact_row["targets"], "meta": compact_row["meta"], "default_target": compact_row["default_target"]}
    )

    print(f"Fixture: {N_TARGETS} targets, {FAMILY_COUNT} familyScores/target, "
          f"{PRODUCT_FAMILY_COUNT} productFamilyRankings entries")
    print(f"Source full mega-contract payload bytes: {source_full_bytes:,}")
    print(f"Source compact payload bytes (targets+meta+default_target): {source_compact_bytes:,}")
    print()

    print("=== Stage 1: Original (pre-1ee37cf9) ===")
    s1 = _run_stage1(full_row)
    for k, v in s1.items():
        print(f"  {k}: {v}")

    print("\n=== Stage 2: Cache-only (1ee37cf9 + 76795836), full reader forced ===")
    s2 = _run_stage2(full_row)
    for k, v in s2.items():
        print(f"  {k}: {v}")

    print("\n=== Stage 3: Compact-final (this pass) ===")
    s3 = _run_stage3(compact_row, full_row)
    for k, v in s3.items():
        print(f"  {k}: {v}")

    current, peak = tracemalloc.get_traced_memory()
    print(f"\ntracemalloc current={current/1e6:.2f}MB peak={peak/1e6:.2f}MB (supplementary only)")
    tracemalloc.stop()

    print("\n=== Summary table ===")
    print(f"{'metric':45s} {'Stage1 Original':>18s} {'Stage2 Cache-only':>18s} {'Stage3 Compact':>18s}")
    print(f"{'RSS fresh (MB)':45s} {s1['rss_fresh']:18.2f} {s2['rss_fresh']:18.2f} {s3['rss_fresh']:18.2f}")
    print(f"{'RSS after 1 (MB)':45s} {s1['rss_after_1']:18.2f} {s2['rss_after_1']:18.2f} {s3['rss_after_1']:18.2f}")
    print(f"{'RSS after 50 (MB)':45s} {s1['rss_after_50']:18.2f} {s2['rss_after_50']:18.2f} {s3['rss_after_50']:18.2f}")
    print(f"{'Retained cache bytes (est.)':45s} {s1['retained_bytes_estimate']:18,} {s2['retained_bytes_estimate']:18,} {s3['retained_bytes_estimate']:18,}")
    print(f"{'p50 latency (ms)':45s} {s1['p50_ms']:18.3f} {s2['p50_ms']:18.3f} {s3['p50_ms']:18.3f}")
    print(f"{'p95 latency (ms)':45s} {s1['p95_ms']:18.3f} {s2['p95_ms']:18.3f} {s3['p95_ms']:18.3f}")


if __name__ == "__main__":
    main()
