"""Reproducible Fusion Strike API/RPC and cache acceptance measurements."""
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


SET_ID = "8cd0a0f0-d17c-4a5c-bc52-47e1723e0699"
THROUGH = "2026-08-28"
START = "1999-01-01"


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
        timings[name] = {
            "samplesMs": samples, "medianMs": statistics.median(samples),
            "p95Ms": percentile_95(samples), "minMs": min(samples), "maxMs": max(samples),
            "returnedHistoricalDates": len(rows),
            "eligibleCurrentConstituents": int(rows[-1]["eligible_universe_count"]) if rows else 0,
        }

    spec = normalize_query_spec(asset="cards", mode="all", set_ids=[SET_ID],
                                segment_ids=["rareHolo"])
    persistent = PersistentMarketExplorerCache(client)
    prepared = PreparedEquivalenceRegistry()

    def builder(previous: str | None, through: str) -> dict:
        return run_market_explorer_query(
            client, mode=spec["mode"], set_ids=spec["setIds"],
            segment_ids=spec["segmentIds"], price_segment_ids=spec["priceSegmentIds"],
            start_date=previous or START, end_date=through,
        )

    first = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache()).execute(
        spec=spec, prepared=prepared, persistent=persistent,
        canonical_through=lambda: resolve_canonical_through(client, spec), novel_builder=builder)
    fresh = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache()).execute(
        spec=spec, prepared=prepared, persistent=persistent,
        canonical_through=lambda: resolve_canonical_through(client, spec), novel_builder=builder)
    same = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache())
    warm_l2 = same.execute(spec=spec, prepared=prepared, persistent=persistent,
                           canonical_through=lambda: resolve_canonical_through(client, spec), novel_builder=builder)
    hot_l1 = same.execute(spec=spec, prepared=prepared, persistent=persistent,
                          canonical_through=lambda: resolve_canonical_through(client, spec), novel_builder=builder)
    payloads = [first.payload, fresh.payload, warm_l2.payload, hot_l1.payload]
    report = {
        "through": THROUGH, "timings": timings,
        "cache": {
            "sources": [first.execution_source, fresh.execution_source,
                        warm_l2.execution_source, hot_l1.execution_source],
            "elapsedMs": [first.elapsed_ms, fresh.elapsed_ms, warm_l2.elapsed_ms, hot_l1.elapsed_ms],
            "samePayload": all(payload == payloads[0] for payload in payloads[1:]),
            "queryFingerprint": query_fingerprint(spec),
            "querySpec": spec,
        },
    }
    output = Path("artifacts/market_explorer_acceptance/20260830_effort1i_fusion_strike/performance-cache.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
