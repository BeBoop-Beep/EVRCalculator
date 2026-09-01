"""Production acceptance and prewarm runner for broad Market Explorer scopes."""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.market_explorer_query_planner import (
    MarketExplorerL1Cache,
    MarketExplorerQueryPlanner,
    PersistentMarketExplorerCache,
    PreparedEquivalenceRegistry,
    resolve_canonical_through,
)
from backend.db.services.pokemon_market_explorer_query_service import run_market_explorer_query
from backend.domain.pokemon.market_explorer_query import normalize_query_spec, query_fingerprint

START = "1999-01-01"


def _stats(samples: list[float]) -> dict[str, Any]:
    ordered = sorted(samples)
    return {
        "samplesMs": samples,
        "medianMs": statistics.median(samples),
        "p95Ms": ordered[max(0, int(len(ordered) * .95 + .999) - 1)],
        "minMs": min(samples), "maxMs": max(samples),
    }


def _builder(client: Any, spec: dict[str, Any]):
    def build(previous: str | None, through: str) -> dict[str, Any]:
        return run_market_explorer_query(
            client, mode=spec["mode"], era_ids=spec["eraIds"], set_ids=spec["setIds"],
            segment_ids=spec["segmentIds"], pokemon_ids=spec["pokemonIds"],
            price_segment_ids=spec["priceSegmentIds"],
            release_age_cohort_ids=spec["releaseAgeCohortIds"], top_n=spec["topN"],
            start_date=previous or START, end_date=through,
        )
    return build


def _execute(client: Any, planner: MarketExplorerQueryPlanner, spec: dict[str, Any]):
    return planner.execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=PersistentMarketExplorerCache(client),
        canonical_through=lambda: resolve_canonical_through(client, spec),
        novel_builder=_builder(client, spec),
    )


def _specs(era_ids: list[str]) -> dict[str, dict[str, Any]]:
    common = {"asset": "cards", "era_ids": era_ids}
    return {
        "full": normalize_query_spec(mode="all", **common),
        "top10": normalize_query_spec(mode="chase", top_n=10, **common),
        "established": normalize_query_spec(mode="all", release_age_cohort_ids=["established"], **common),
        "rarity": normalize_query_spec(mode="all", segment_ids=["rareHolo"], **common),
        "premium": normalize_query_spec(mode="all", price_segment_ids=["premium"], **common),
    }


def accept_scope(*, era_ids: list[str], l2_samples: int, l1_samples: int,
                 reset: bool, maintain: bool) -> dict[str, Any]:
    control = create_service_role_client()
    specs = _specs(era_ids)
    fingerprints = [query_fingerprint(spec) for spec in specs.values()]
    if reset:
        control.table("pokemon_market_explorer_query_cache").delete().in_(
            "query_fingerprint", fingerprints
        ).execute()

    report: dict[str, Any] = {}
    for name, spec in specs.items():
        cold_client = create_service_role_client()
        cold = _execute(cold_client, MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache()), spec)
        payload_bytes = len(json.dumps(cold.payload, separators=(",", ":"), default=str).encode())

        l2_times, l2_sources = [], []
        for _ in range(l2_samples):
            client = create_service_role_client()
            started = time.perf_counter()
            result = _execute(client, MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache()), spec)
            l2_times.append((time.perf_counter() - started) * 1000)
            l2_sources.append(result.execution_source)

        hot_client = create_service_role_client()
        hot_planner = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache())
        seed = _execute(hot_client, hot_planner, spec)
        l1_times, l1_sources = [], []
        for _ in range(l1_samples):
            started = time.perf_counter()
            result = _execute(hot_client, hot_planner, spec)
            l1_times.append((time.perf_counter() - started) * 1000)
            l1_sources.append(result.execution_source)

        fingerprint = query_fingerprint(spec)
        if maintain and name in ("full", "top10"):
            (control.table("pokemon_market_explorer_query_cache").update({"cache_kind": "maintained"})
             .eq("query_fingerprint", fingerprint).eq("status", "ready").execute())
        row = list((control.table("pokemon_market_explorer_query_cache")
                    .select("query_fingerprint,status,cache_kind,computed_through")
                    .eq("query_fingerprint", fingerprint).limit(1).execute()).data or [])
        report[name] = {
            "spec": spec, "fingerprint": fingerprint, "coldSource": cold.execution_source,
            "coldBuilderMs": cold.elapsed_ms, "payloadBytes": payload_bytes,
            "l2": {**_stats(l2_times), "sources": l2_sources},
            "l1": {**_stats(l1_times), "sources": l1_sources, "seedSource": seed.execution_source},
            "persistentRows": row,
        }
        print(json.dumps({"event": "cache_case_complete", "name": name,
                          "coldMs": cold.elapsed_ms, "l2MedianMs": statistics.median(l2_times),
                          "l1MedianMs": statistics.median(l1_times)}), flush=True)
    return {"eraIds": era_ids, "cases": report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--era-id", action="append", required=True)
    parser.add_argument("--l2-samples", type=int, default=10)
    parser.add_argument("--l1-samples", type=int, default=20)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--maintain", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = accept_scope(era_ids=args.era_id, l2_samples=args.l2_samples,
                          l1_samples=args.l1_samples, reset=args.reset,
                          maintain=args.maintain)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
