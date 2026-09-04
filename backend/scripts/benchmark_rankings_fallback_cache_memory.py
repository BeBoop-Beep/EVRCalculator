"""Memory benchmark for `/explore/rip-statistics/targets` and its rankings
fallback cache — Phase A/E of docs/PRODUCTION_BACKEND_MEMORY_P0_2026-09-04.md.

Runs the REAL `get_pokemon_explore_rankings_snapshot_payload()` reader (not a
mock of its internals) against a synthetic-but-realistically-shaped snapshot
row, sized to match production's `pokemon_explore_rankings_snapshot_latest`
mega-contract: 200 targets, each carrying a `setRipV1` block with a
`familyScores` list, plus a top-level `productFamilyRankings` block — the
same fields the incident's live payload carried, reconstructed here because
this environment has no production DB credentials. Uses `psutil` for RSS
(the metric Render actually restarts on); `tracemalloc` is supplementary.

Run locally without --reload:
    python -m backend.scripts.benchmark_rankings_fallback_cache_memory
"""
from __future__ import annotations

import gc
import time
import tracemalloc
from typing import Any, Dict, List

import psutil

from backend.db.services import pokemon_public_snapshot_service as svc
from backend.db.services.public_rip_publication_contract import canonical_publication_identity

PROCESS = psutil.Process()


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
        {
            "family": f"family-{i}",
            "skuCount": 12,
            "score": 0.5,
            "rank": i + 1,
            "cohortSize": n,
        }
        for i in range(n)
    ]


def _target(i: int, family_count: int) -> Dict[str, Any]:
    families = _family_scores(family_count)
    participating = [f["family"] for f in families]
    return {
        "id": f"set-{i}",
        "target_id": f"set-{i}",
        "target_type": "set",
        "name": f"Synthetic Set {i}",
        "is_opening_set": True,
        "setRipV1": {
            "rankable": True,
            "cohortSize": family_count,
            "familyScores": families,
            "participatingFamilies": participating,
            "participatingFamilyCount": len(participating),
        },
        # Padding to approximate real per-target payload weight (price
        # history points, checklist rows, etc.) without needing live data.
        "history": [{"date": f"2026-01-{d:02d}", "value": d * 1.1} for d in range(1, 29)],
    }


def _build_row(n_targets: int = 200, family_count: int = 25) -> Dict[str, Any]:
    targets = [_target(i, family_count) for i in range(n_targets)]
    product_family_rankings = {
        "families": {
            f"family-{i}": {"rank": i, "score": 0.5, "skuCount": 12}
            for i in range(family_count * 4)
        }
    }
    payload = {
        "targets": targets,
        "meta": _identity_meta(),
        "productFamilyRankings": product_family_rankings,
    }
    return {
        "updated_at": "2026-09-04T15:08:00+00:00",
        "ranking_payload_json": payload,
        "default_target_json": {"target_id": "set-0", "target_type": "set"},
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


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers

    def table(self, table_name):
        return _Query(table_name, self.handlers)


def _install_client(row):
    client = _Client({"pokemon_explore_rankings_snapshot_latest": lambda _q: [row]})
    svc.service_read_client = client  # module-level rebind, this is a standalone process
    svc.create_short_timeout_service_client = lambda: client
    svc._enrich_rankings_payload_with_checklist_set_values = lambda payload: payload


def _report(label: str, t0_rss: float, t1_rss: float, elapsed_s: float) -> None:
    print(f"{label:55s} rss={t1_rss:9.2f}MB  delta={t1_rss - t0_rss:+8.2f}MB  wall={elapsed_s*1000:8.2f}ms")


def main() -> None:
    tracemalloc.start()
    svc._reset_rankings_fallback_cache_for_tests()
    row = _build_row()
    _install_client(row)

    rss0 = _rss_mb()
    print(f"RSS before first request: {rss0:.2f}MB")

    t0 = time.perf_counter()
    svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
    elapsed = time.perf_counter() - t0
    rss1 = _rss_mb()
    _report("after first limit=200 request", rss0, rss1, elapsed)

    t0 = time.perf_counter()
    for _ in range(50):
        svc.get_pokemon_explore_rankings_snapshot_payload(limit=200)
    elapsed = time.perf_counter() - t0
    rss2 = _rss_mb()
    _report("after 50 more identical limit=200 requests", rss1, rss2, elapsed)

    t0 = time.perf_counter()
    for lim in list(range(1, 201)):
        svc.get_pokemon_explore_rankings_snapshot_payload(limit=lim)
    elapsed = time.perf_counter() - t0
    rss3 = _rss_mb()
    _report("after 200 requests spanning every distinct limit 1..200", rss2, rss3, elapsed)

    cache = svc._RANKINGS_FALLBACK_CACHE
    print(f"cache slot keys: {sorted(cache.keys())} (single slot, not per-limit)")
    print(f"cached raw_targets length: {len(cache['raw_targets'])}")

    current, peak = tracemalloc.get_traced_memory()
    print(f"tracemalloc current={current/1e6:.2f}MB peak={peak/1e6:.2f}MB (supplementary only)")
    tracemalloc.stop()

    print(f"\nTOTAL RSS delta over run: {rss3 - rss0:+.2f}MB")


if __name__ == "__main__":
    main()
