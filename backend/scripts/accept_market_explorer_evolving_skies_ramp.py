"""Reproducible Evolving Skies RPC and cache acceptance measurements."""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

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


SET_ID = "93212749-ce0e-498e-975e-7d947a3448ce"
THROUGH = "2026-08-28"
START = "1999-01-01"
OUTPUT = Path("artifacts/market_explorer_acceptance/20260831_effort1i_evolving_skies/performance-cache.json")


def percentile_95(values: list[float]) -> float:
    return sorted(values)[-1] if len(values) < 20 else statistics.quantiles(values, n=20)[18]


def main() -> None:
    client = create_service_role_client()
    base = {
        "p_set_ids": [SET_ID], "p_card_ids": None, "p_pokemon_ids": None,
        "p_segment_ids": None, "p_price_segment_ids": None,
        "p_release_age_cohort_ids": None,
    }
    cases = {
        "full": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": None},
        "top10": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": 10},
        "current": {"p_start_date": THROUGH, "p_end_date": THROUGH, "p_top_n": None},
        "currentTop25": {"p_start_date": THROUGH, "p_end_date": THROUGH, "p_top_n": 25},
        "rarityRareHolo": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": None,
                           "p_segment_ids": ["rareHolo"]},
        "pricePremium": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": None,
                         "p_price_segment_ids": ["premium"]},
        "releaseEstablished": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": None,
                               "p_release_age_cohort_ids": ["established"]},
    }
    timings = {}
    for name, overrides in cases.items():
        samples, rows = [], []
        for _ in range(5):
            started = time.perf_counter()
            rows = list(client.rpc("get_pokemon_market_explorer_filtered_cohort",
                                   {**base, **overrides}).execute().data or [])
            samples.append((time.perf_counter() - started) * 1000)
        encoded = json.dumps(rows, separators=(",", ":"), default=str).encode("utf-8")
        timings[name] = {
            "samplesMs": samples, "medianMs": statistics.median(samples),
            "p95Ms": percentile_95(samples), "minMs": min(samples), "maxMs": max(samples),
            "payloadBytes": len(encoded), "returnedHistoricalDates": len(rows),
            "eligibleCurrentConstituents": int(rows[-1]["eligible_universe_count"]) if rows else 0,
        }

    spec = normalize_query_spec(asset="cards", mode="all", set_ids=[SET_ID])
    persistent = PersistentMarketExplorerCache(client)
    prepared = PreparedEquivalenceRegistry()

    def builder(previous: str | None, through: str) -> dict:
        return run_market_explorer_query(client, mode=spec["mode"], set_ids=spec["setIds"],
                                         start_date=previous or START, end_date=through)

    planner = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache())
    first = planner.execute(spec=spec, prepared=prepared, persistent=persistent,
                            canonical_through=lambda: resolve_canonical_through(client, spec), novel_builder=builder)
    fresh = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache()).execute(
        spec=spec, prepared=prepared, persistent=persistent,
        canonical_through=lambda: resolve_canonical_through(client, spec), novel_builder=builder)
    hot_l1 = planner.execute(spec=spec, prepared=prepared, persistent=persistent,
                             canonical_through=lambda: resolve_canonical_through(client, spec), novel_builder=builder)
    payloads = [first.payload, fresh.payload, hot_l1.payload]
    fingerprint = query_fingerprint(spec)
    cache_rows = list((client.table("pokemon_market_explorer_query_cache")
                       .select("query_fingerprint,status,computed_through")
                       .eq("query_fingerprint", fingerprint).execute()).data or [])
    report = {
        "setId": SET_ID, "through": THROUGH, "timings": timings,
        "cache": {
            "sources": [first.execution_source, fresh.execution_source, hot_l1.execution_source],
            "elapsedMs": [first.elapsed_ms, fresh.elapsed_ms, hot_l1.elapsed_ms],
            "samePayload": all(payload == payloads[0] for payload in payloads[1:]),
            "queryFingerprint": fingerprint, "querySpec": spec,
            "persistentRows": cache_rows,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
