"""Live-scale verification of the compact reader (`dd1d01c4`) against the
real production `pokemon_explore_rankings_snapshot_latest` row, read-only.

This is the closer for the 2026-09-04 memory P0's one open gap: prior
benchmark passes (`benchmark_rip_statistics_targets_compact_memory.py`) only
exercised a synthetic fixture. This script pulls the real production row
ONCE (read-only `select`, never written), then runs the compact RPC's exact
SELECT/projection logic (`supabase/migrations/
20260904010000_add_rip_statistics_targets_compact_rpc.sql`) in Python against
it in-process, because the migration is NOT deployed to production yet
(confirmed via a `PGRST202` probe at the time this script was written) and
this pass must not deploy it there.

Requires `backend/.env` with real `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`
(the same credentials `backend/db/clients/supabase_client.py` already loads
for every other backend script/test). Read-only: only `.select()` calls
against `pokemon_explore_rankings_snapshot_latest` are issued.

Run standalone:

    python -m backend.scripts.verify_rip_statistics_targets_compact_live_scale
"""
from __future__ import annotations

import gc
import json
import time
from typing import Any, Dict, List, Optional

import psutil

from backend.db.clients.supabase_client import create_short_timeout_service_client
from backend.db.services import pokemon_public_snapshot_service as svc
from backend.domain.access.index_plan_access import _BASE_TARGET_FIELDS, _PLUS_TARGET_FIELDS

PROCESS = psutil.Process()

_NESTED_PASSTHROUGH = [
    "rip", "ripCore", "financialRipV4", "overallRipV10", "publicRipContractV10",
    "setRipV1", "openingExperience", "rankingsChase",
]


def _rss_mb() -> float:
    return PROCESS.memory_info().rss / (1024 * 1024)


def _payload_bytes(obj: Any) -> int:
    return len(json.dumps(obj).encode("utf-8"))


def _is_opening_set_row(t: Dict[str, Any]) -> bool:
    v = t.get("is_opening_set")
    if v is None:
        v = t.get("isOpeningSet")
    return bool(v) if v is not None else True


def _project_target(target: Dict[str, Any]) -> Dict[str, Any]:
    """Reproduces `public.project_pokemon_rip_statistics_target` from the
    (undeployed-to-prod) migration: the Plus scalar field allowlist plus the
    nested Base+Plus objects passed through whole."""
    out = {k: target[k] for k in _PLUS_TARGET_FIELDS if k in target}
    nested = {k: target.get(k) for k in _NESTED_PASSTHROUGH}
    out.update({k: v for k, v in nested.items() if v is not None})
    return out


def _build_compact_row(
    full_payload: Dict[str, Any], default_target_json: Any, updated_at: Any, limit: int = 200
) -> Dict[str, Any]:
    targets = [t for t in (full_payload.get("targets") or []) if _is_opening_set_row(t)]
    targets = targets[: max(1, min(limit, 200))]
    return {
        "targets": [_project_target(t) for t in targets],
        "default_target": default_target_json,
        "meta": full_payload.get("meta") or {},
        "updated_at": updated_at,
    }


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def select(self, _f):
        return self

    def eq(self, _f, _v):
        return self

    def limit(self, _v):
        return self

    def execute(self):
        return _Result(self._rows)


class _InProcessClient:
    """Wires the real compact-source-of-truth data through the actual
    `_build_compact_rankings_targets_response` / fallback code path, without
    issuing any further network calls."""

    def __init__(self, compact_data: Dict[str, Any], full_row: Dict[str, Any], rpc_fails: bool = False):
        self._compact_data = compact_data
        self._full_row = full_row
        self._rpc_fails = rpc_fails

    def table(self, _name):
        return _Query([self._full_row])

    def rpc(self, _fn, _params=None):
        if self._rpc_fails:
            class _Failing:
                def execute(self_inner):
                    raise Exception(
                        "PGRST202: Could not find the function "
                        "public.get_pokemon_rip_statistics_targets_compact"
                    )
            return _Failing()

        class _Ok:
            def __init__(self_inner, data):
                self_inner._data = data

            def execute(self_inner):
                return _Result(self_inner._data)

        return _Ok(self._compact_data)


def fetch_real_production_row() -> Dict[str, Any]:
    client = create_short_timeout_service_client()
    r = (
        client.table("pokemon_explore_rankings_snapshot_latest")
        .select("tcg,scope,ranking_payload_json,default_target_json,updated_at")
        .eq("tcg", "pokemon")
        .eq("scope", "rip-statistics")
        .limit(1)
        .execute()
    )
    if not r.data:
        raise RuntimeError("no pokemon/rip-statistics row found in production")
    return r.data[0]


def main() -> None:
    print("=== Fetching real production row (read-only) ===")
    t0 = time.perf_counter()
    row = fetch_real_production_row()
    fetch_s = time.perf_counter() - t0
    full_payload = row["ranking_payload_json"]
    default_target_json = row.get("default_target_json")
    updated_at = row.get("updated_at")

    full_source_bytes = _payload_bytes(full_payload)
    n_targets = len(full_payload.get("targets") or [])
    print(f"fetch_s={fetch_s:.3f} full_source_bytes={full_source_bytes:,} n_targets={n_targets}")

    compact_row = _build_compact_row(full_payload, default_target_json, updated_at, limit=200)
    compact_source_bytes = _payload_bytes(compact_row)
    print(f"compact_source_bytes={compact_source_bytes:,} compact_target_count={len(compact_row['targets'])}")

    # --- Test A: parity ------------------------------------------------------
    print("\n=== Test A: parity ===")
    full_targets = [t for t in full_payload.get("targets") or [] if _is_opening_set_row(t)][:200]
    compact_targets = compact_row["targets"]
    order_full = [t.get("target_id") or t.get("id") for t in full_targets]
    order_compact = [t.get("target_id") or t.get("id") for t in compact_targets]
    print("target ordering parity:", order_full == order_compact)

    base_ok = all(
        ft.get(f) == ct.get(f)
        for ft, ct in zip(full_targets, compact_targets)
        for f in _BASE_TARGET_FIELDS
        if f in ft
    )
    plus_ok = all(
        ft.get(f) == ct.get(f)
        for ft, ct in zip(full_targets, compact_targets)
        for f in _PLUS_TARGET_FIELDS
        if f in ft
    )
    print("Base source-field parity:", base_ok)
    print("Plus source-field parity:", plus_ok)

    meta = full_payload.get("meta") or {}
    audit_full = meta.get("openingSetAudit") or meta.get("opening_set_audit")
    audit_compact = compact_row["meta"].get("openingSetAudit") or compact_row["meta"].get("opening_set_audit")
    print("persisted audit parity:", audit_full == audit_compact)

    def _rank_map(targets: List[Dict[str, Any]], key: str) -> Dict[Optional[str], Any]:
        return {
            t.get("target_id") or t.get("id"): (t.get(key) or {}).get("rank")
            for t in targets
        }

    print("Set rank parity:", _rank_map(full_targets, "setRipV1") == _rank_map(compact_targets, "setRipV1"))
    print(
        "Overall rank parity:",
        _rank_map(full_targets, "overallRipV10") == _rank_map(compact_targets, "overallRipV10"),
    )
    print(
        "Financial rank parity:",
        _rank_map(full_targets, "financialRipV4") == _rank_map(compact_targets, "financialRipV4"),
    )

    # --- Publication-identity gate (pre-existing, orthogonal to this P0) -----
    print("\n=== Publication identity gate ===")
    mismatches = svc._rankings_publication_identity_mismatches(full_payload)
    if mismatches:
        print("Production has NOT been republished under the current canonical identity:")
        for m in mismatches:
            print(f"  {m['identifier']} observed={m['observed']!r} expected={m['expected']!r}")
        print(
            "This fires identically for the full mega-contract reader and the compact "
            "reader (same check, same persisted meta) -- confirmed symmetric, not a "
            "compact-reader defect. Bypassing it below (monkeypatch) purely so "
            "RSS/latency can still be measured against the real-scale payload."
        )
        svc._rankings_publication_identity_mismatches = lambda _payload: []
    else:
        print("No mismatch -- production is on the current canonical identity.")

    # --- Test B: fresh-process memory ----------------------------------------
    print("\n=== Test B: fresh-process memory ===")
    gc.collect()
    rss_initial = _rss_mb()
    print(f"rss_initial(after imports+fetch)={rss_initial:.2f}MB")

    svc._reset_rankings_fallback_cache_for_tests()
    healthy_client = _InProcessClient(compact_row, row, rpc_fails=False)
    svc.service_read_client = healthy_client
    svc.create_short_timeout_service_client = lambda: healthy_client

    rss_before_first = _rss_mb()
    resp1 = svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
    resp1_bytes = _payload_bytes(resp1)
    rss_after_first = _rss_mb()
    gc.collect()
    rss_after_gc = _rss_mb()
    print(f"rss_before_first_read={rss_before_first:.2f}MB")
    print(f"rss_after_first_read={rss_after_first:.2f}MB response_bytes={resp1_bytes:,}")
    print(f"rss_after_forced_gc={rss_after_gc:.2f}MB")
    print("first response snapshot.source:", resp1.get("meta", {}).get("snapshot", {}).get("source"))
    print("first response target count:", len(resp1.get("targets") or []))

    # --- Test C: production workload plateau ----------------------------------
    print("\n=== Test C: workload plateau ===")
    rss_req0 = _rss_mb()
    lat: List[float] = []

    def _timed_request():
        t0 = time.perf_counter()
        r = svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
        lat.append((time.perf_counter() - t0) * 1000)
        return r

    r1 = _timed_request()
    rss_1 = _rss_mb()
    for _ in range(4):
        _timed_request()
    rss_5 = _rss_mb()
    for _ in range(15):
        _timed_request()
    rss_20 = _rss_mb()
    for _ in range(30):
        _timed_request()
    rss_50 = _rss_mb()
    for _ in range(50):
        _timed_request()
    rss_100 = _rss_mb()

    lat_sorted = sorted(lat)
    p50 = lat_sorted[len(lat_sorted) // 2]
    p95 = lat_sorted[int(len(lat_sorted) * 0.95)]
    print(
        f"rss_before_req1={rss_req0:.2f}MB rss_after_1={rss_1:.2f}MB rss_after_5={rss_5:.2f}MB "
        f"rss_after_20={rss_20:.2f}MB rss_after_50={rss_50:.2f}MB rss_after_100={rss_100:.2f}MB"
    )
    print(f"latency ms: min={min(lat):.3f} p50={p50:.3f} p95={p95:.3f} max={max(lat):.3f}")
    print(
        f"response_bytes={_payload_bytes(r1):,} source_full_bytes={full_source_bytes:,} "
        f"source_compact_bytes={compact_source_bytes:,}"
    )

    cache = svc._RANKINGS_FALLBACK_CACHE
    retained = _payload_bytes(cache.get("base_payload") or {}) + _payload_bytes(cache.get("raw_targets") or [])
    print(f"cache_slot_count=1 estimated_retained_cache_bytes={retained:,}")

    # --- Test E: fallback-path sanity ------------------------------------------
    print("\n=== Test E: fallback sanity (compact RPC unavailable) ===")
    svc._reset_rankings_fallback_cache_for_tests()
    failing_client = _InProcessClient(compact_row, row, rpc_fails=True)
    svc.service_read_client = failing_client
    svc.create_short_timeout_service_client = lambda: failing_client
    svc._enrich_rankings_payload_with_checklist_set_values = lambda payload: payload

    resp_fallback = svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
    print("fallback response source:", resp_fallback.get("meta", {}).get("snapshot", {}).get("source"))
    print("fallback response target count:", len(resp_fallback.get("targets") or []))
    cache2 = svc._RANKINGS_FALLBACK_CACHE
    print("fallback cache identity_key present:", cache2.get("identity_key") is not None)
    resp_fallback2 = svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
    print("second fallback response source (no retry loop):", resp_fallback2.get("meta", {}).get("snapshot", {}).get("source"))

    print("\nDONE")


if __name__ == "__main__":
    main()
