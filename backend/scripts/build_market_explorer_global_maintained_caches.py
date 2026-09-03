"""One-off Global All Raw / Global Top 10 maintained-cache build, pinned to
the 2026-09-02 daily-projection watermark (canonical_through currently reads
2026-09-03, one day ahead of pokemon_market_explorer_card_daily_coverage's
computed_through, a same-day pipeline-lag artifact unrelated to this
session's two root-cause fixes). Uses only the real application path:
MarketExplorerQueryPlanner + PersistentMarketExplorerCache + run_market_explorer_query.
"""
import json, time, statistics
from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.market_explorer_query_planner import (
    MarketExplorerL1Cache, MarketExplorerQueryPlanner, PersistentMarketExplorerCache,
    PreparedEquivalenceRegistry,
)
from backend.db.services.pokemon_market_explorer_query_service import run_market_explorer_query
from backend.domain.pokemon.market_explorer_query import normalize_query_spec, query_fingerprint

PINNED_THROUGH = "2026-09-02"
START = "2026-04-07"  # projection-covered lower bound for the full 165-set authority


def builder(client, spec):
    def build(previous, through):
        return run_market_explorer_query(
            client, mode=spec["mode"], era_ids=spec["eraIds"], set_ids=spec["setIds"],
            segment_ids=spec["segmentIds"], pokemon_ids=spec["pokemonIds"],
            price_segment_ids=spec["priceSegmentIds"],
            release_age_cohort_ids=spec["releaseAgeCohortIds"], top_n=spec["topN"],
            start_date=previous or START, end_date=through)
    return build


def execute(client, planner, spec, lease=300, summary=False):
    return planner.execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=PersistentMarketExplorerCache(client, build_lease_seconds=lease),
        canonical_through=lambda: PINNED_THROUGH,
        novel_builder=builder(client, spec), summary=summary)


def stats(samples):
    ordered = sorted(samples)
    return {"samplesMs": samples, "medianMs": statistics.median(samples),
            "p95Ms": ordered[max(0, int(len(ordered) * .95 + .999) - 1)],
            "minMs": min(samples), "maxMs": max(samples)}


def build_one(control, name, spec, l2_samples=2, l1_samples=2):
    cold_client = create_service_role_client()
    started = time.perf_counter()
    cold = execute(cold_client, MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache()), spec)
    cold_ms = (time.perf_counter() - started) * 1000
    l2_times, l2_sources = [], []
    for _ in range(l2_samples):
        client = create_service_role_client()
        t0 = time.perf_counter()
        result = execute(client, MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache()), spec)
        l2_times.append((time.perf_counter() - t0) * 1000)
        l2_sources.append(result.execution_source)
    hot_client = create_service_role_client()
    hot_planner = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache())
    execute(hot_client, hot_planner, spec)
    l1_times, l1_sources = [], []
    for _ in range(l1_samples):
        t0 = time.perf_counter()
        result = execute(hot_client, hot_planner, spec)
        l1_times.append((time.perf_counter() - t0) * 1000)
        l1_sources.append(result.execution_source)
    fingerprint = query_fingerprint(spec)
    (control.table("pokemon_market_explorer_query_cache")
     .update({"cache_kind": "maintained"}).eq("query_fingerprint", fingerprint)
     .eq("status", "ready").execute())
    row = list((control.table("pokemon_market_explorer_query_cache")
                .select("query_fingerprint,status,cache_kind,computed_through,constituent_count,eligible_universe_count")
                .eq("query_fingerprint", fingerprint).limit(1).execute()).data or [])
    return {"name": name, "fingerprint": fingerprint, "coldMs": cold_ms,
            "coldSource": cold.execution_source,
            "l2": {**stats(l2_times), "sources": l2_sources},
            "l1": {**stats(l1_times), "sources": l1_sources},
            "persistentRows": row}


def main():
    control = create_service_role_client()
    results = {}
    for mode, top_n, name in [("all", None, "global_allraw"), ("chase", 10, "global_top10")]:
        spec = normalize_query_spec(mode=mode, asset="cards", era_ids=[], set_ids=[], top_n=top_n)
        result = build_one(control, name, spec)
        results[name] = result
        print(json.dumps({"event": "case_complete", "name": name, "coldMs": result["coldMs"],
                          "coldSource": result["coldSource"], "persistentRows": result["persistentRows"]}, default=str), flush=True)
    from pathlib import Path
    Path("backend/artifacts/market_explorer_acceptance/prompt5_build_global.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    print("DONE")


if __name__ == "__main__":
    main()
