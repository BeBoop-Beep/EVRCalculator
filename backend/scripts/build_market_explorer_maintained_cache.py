"""Production builder/prewarm runner for Market Explorer maintained caches.

Generalizes accept_market_explorer_cache_first_era.py to global scope (no
era/set filter) and to a smaller, faster sample count suitable for building
many per-era maintained caches in one pass. Uses only the real application
builder/lease/publish path (MarketExplorerQueryPlanner + PersistentMarketExplorerCache
+ run_market_explorer_query) -- no raw SQL cache payload writes.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.market_explorer_query_planner import (
    MarketExplorerL1Cache, MarketExplorerQueryPlanner, PersistentMarketExplorerCache,
    PreparedEquivalenceRegistry, resolve_canonical_through,
)
from backend.db.services.pokemon_market_explorer_query_service import run_market_explorer_query
from backend.domain.pokemon.market_explorer_query import normalize_query_spec, query_fingerprint

START = "1999-01-01"


def stats(samples: list[float]) -> dict[str, Any]:
    ordered = sorted(samples)
    return {"samplesMs": samples, "medianMs": statistics.median(samples),
            "p95Ms": ordered[max(0, int(len(ordered) * .95 + .999) - 1)],
            "minMs": min(samples), "maxMs": max(samples)}


def builder(client: Any, spec: dict[str, Any]):
    def build(previous: str | None, through: str) -> dict[str, Any]:
        return run_market_explorer_query(
            client, mode=spec["mode"], era_ids=spec["eraIds"], set_ids=spec["setIds"],
            segment_ids=spec["segmentIds"], pokemon_ids=spec["pokemonIds"],
            price_segment_ids=spec["priceSegmentIds"],
            release_age_cohort_ids=spec["releaseAgeCohortIds"], top_n=spec["topN"],
            start_date=previous or START, end_date=through)
    return build


def execute(client: Any, planner: MarketExplorerQueryPlanner, spec: dict[str, Any],
            lease: int = 300, summary: bool = False):
    return planner.execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=PersistentMarketExplorerCache(client, build_lease_seconds=lease),
        canonical_through=lambda: resolve_canonical_through(client, spec),
        novel_builder=builder(client, spec), summary=summary)


def build_one(control: Any, name: str, spec: dict[str, Any], *, l2_samples: int, l1_samples: int,
              summary: bool) -> dict[str, Any]:
    cold_client = create_service_role_client()
    cold = execute(cold_client, MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache()), spec,
                   summary=summary)
    payload_bytes = len(json.dumps(cold.payload, separators=(",", ":"), default=str).encode())
    l2_times, l2_sources = [], []
    for _ in range(l2_samples):
        client = create_service_role_client()
        started = time.perf_counter()
        result = execute(client, MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache()), spec,
                         summary=summary)
        l2_times.append((time.perf_counter() - started) * 1000)
        l2_sources.append(result.execution_source)
    hot_client = create_service_role_client()
    hot_planner = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache())
    seed = execute(hot_client, hot_planner, spec, summary=summary)
    l1_times, l1_sources = [], []
    for _ in range(l1_samples):
        started = time.perf_counter()
        result = execute(hot_client, hot_planner, spec, summary=summary)
        l1_times.append((time.perf_counter() - started) * 1000)
        l1_sources.append(result.execution_source)
    fingerprint = query_fingerprint(spec)
    (control.table("pokemon_market_explorer_query_cache")
     .update({"cache_kind": "maintained"}).eq("query_fingerprint", fingerprint)
     .eq("status", "ready").execute())
    row = list((control.table("pokemon_market_explorer_query_cache")
                .select("query_fingerprint,status,cache_kind,computed_through,constituent_count")
                .eq("query_fingerprint", fingerprint).limit(1).execute()).data or [])
    return {"name": name, "spec": spec, "fingerprint": fingerprint,
            "coldSource": cold.execution_source, "coldBuilderMs": cold.elapsed_ms,
            "payloadBytes": payload_bytes,
            "l2": {**stats(l2_times), "sources": l2_sources} if l2_times else None,
            "l1": {**stats(l1_times), "sources": l1_sources,
                   "seedSource": seed.execution_source} if l1_times else None,
            "persistentRows": row}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--era-id", action="append", default=[])
    parser.add_argument("--set-id", action="append", default=[])
    parser.add_argument("--mode", action="append", default=[], choices=["all", "chase"],
                        help="repeatable; default is all+chase for global-style runs")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--label", required=True)
    parser.add_argument("--l2-samples", type=int, default=3)
    parser.add_argument("--l1-samples", type=int, default=3)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    modes = args.mode or ["all"]

    control = create_service_role_client()
    cases: dict[str, Any] = {}
    for mode in modes:
        top_n = args.top_n if mode == "chase" else None
        spec = normalize_query_spec(mode=mode, asset="cards", era_ids=args.era_id,
                                     set_ids=args.set_id, top_n=top_n)
        name = "top10" if mode == "chase" else "full"
        result = build_one(control, name, spec, l2_samples=args.l2_samples,
                           l1_samples=args.l1_samples, summary=args.summary)
        cases[name] = result
        print(json.dumps({"event": "case_complete", "label": args.label, "name": name,
                          "coldMs": result["coldBuilderMs"], "coldSource": result["coldSource"],
                          "persistentRows": result["persistentRows"]}), flush=True)

    report = {"label": args.label, "eraIds": args.era_id, "setIds": args.set_id, "cases": cases}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"event": "done", "label": args.label}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
