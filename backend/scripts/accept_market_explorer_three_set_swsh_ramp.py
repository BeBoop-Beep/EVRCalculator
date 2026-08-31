"""Three-set Sword & Shield RPC, planner, and cache acceptance measurements."""
from __future__ import annotations

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

SETS = [
    "8cd0a0f0-d17c-4a5c-bc52-47e1723e0699",
    "93212749-ce0e-498e-975e-7d947a3448ce",
    "1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890",
]
CHILLING = [SETS[-1]]
START, THROUGH = "1999-01-01", "2026-08-28"
OUTPUT = Path("artifacts/market_explorer_acceptance/20260831_effort1i_three_set_swsh/performance-cache.json")


def p95(values: list[float]) -> float:
    return sorted(values)[-1]


def rpc_cases(client: Any, set_ids: list[str], cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    base = {"p_set_ids": set_ids, "p_card_ids": None, "p_pokemon_ids": None,
            "p_segment_ids": None, "p_price_segment_ids": None,
            "p_release_age_cohort_ids": None}
    result = {}
    for name, overrides in cases.items():
        samples, rows = [], []
        for _ in range(5):
            started = time.perf_counter()
            rows = list(client.rpc("get_pokemon_market_explorer_filtered_cohort",
                                   {**base, **overrides}).execute().data or [])
            samples.append((time.perf_counter() - started) * 1000)
        result[name] = {
            "samplesMs": samples, "medianMs": statistics.median(samples),
            "p95Ms": p95(samples), "minMs": min(samples), "maxMs": max(samples),
            "payloadBytes": len(json.dumps(rows, separators=(",", ":"), default=str).encode()),
            "historicalDates": len(rows),
            "eligibleCurrentConstituents": int(rows[-1]["eligible_universe_count"]) if rows else 0,
        }
    return result


def spec_for(**kwargs: Any) -> dict[str, Any]:
    return normalize_query_spec(asset="cards", set_ids=SETS, mode="chase" if kwargs.get("top_n") else "all", **kwargs)


def cached(client: Any, spec: dict[str, Any], include_l1: bool) -> dict[str, Any]:
    persistent, prepared = PersistentMarketExplorerCache(client), PreparedEquivalenceRegistry()

    def builder(previous: str | None, through: str) -> dict[str, Any]:
        return run_market_explorer_query(
            client, mode=spec["mode"], set_ids=spec["setIds"], segment_ids=spec["segmentIds"],
            pokemon_ids=spec["pokemonIds"], price_segment_ids=spec["priceSegmentIds"],
            release_age_cohort_ids=spec["releaseAgeCohortIds"], top_n=spec["topN"],
            start_date=previous or START, end_date=through,
        )

    planner = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache())
    novel = planner.execute(spec=spec, prepared=prepared, persistent=persistent,
                            canonical_through=lambda: resolve_canonical_through(client, spec), novel_builder=builder)
    l2 = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache()).execute(
        spec=spec, prepared=prepared, persistent=persistent,
        canonical_through=lambda: resolve_canonical_through(client, spec), novel_builder=builder)
    executions = [novel, l2]
    if include_l1:
        executions.append(planner.execute(spec=spec, prepared=prepared, persistent=persistent,
                                          canonical_through=lambda: resolve_canonical_through(client, spec),
                                          novel_builder=builder))
    fingerprint = query_fingerprint(spec)
    rows = list((client.table("pokemon_market_explorer_query_cache")
                 .select("query_fingerprint,status,computed_through")
                 .eq("query_fingerprint", fingerprint).execute()).data or [])
    return {"sources": [x.execution_source for x in executions],
            "elapsedMs": [x.elapsed_ms for x in executions],
            "samePayload": all(x.payload == executions[0].payload for x in executions[1:]),
            "fingerprint": fingerprint, "persistentRows": rows, "spec": spec}


def main() -> None:
    client = create_service_role_client()
    standard = {
        "full": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": None},
        "top10": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": 10},
        "current": {"p_start_date": THROUGH, "p_end_date": THROUGH, "p_top_n": None},
        "currentTop25": {"p_start_date": THROUGH, "p_end_date": THROUGH, "p_top_n": 25},
        "rareHolo": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": None,
                     "p_segment_ids": ["rareHolo"]},
        "premium": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": None,
                    "p_price_segment_ids": ["premium"]},
        "established": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": None,
                        "p_release_age_cohort_ids": ["established"]},
    }
    compounds = {
        "rarityPremium": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": None,
                          "p_segment_ids": ["rareUltra"], "p_price_segment_ids": ["premium"]},
        "rarityTop10": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": 10,
                        "p_segment_ids": ["rareHolo"]},
        "premiumTop10": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": 10,
                         "p_price_segment_ids": ["premium"]},
        "calyrexRarity": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": None,
                          "p_pokemon_ids": [898], "p_segment_ids": ["rareUltra"]},
        "establishedPremium": {"p_start_date": START, "p_end_date": THROUGH, "p_top_n": None,
                               "p_release_age_cohort_ids": ["established"],
                               "p_price_segment_ids": ["premium"]},
    }
    full_spec = spec_for()
    compound_spec = spec_for(segment_ids=["rareUltra"], price_segment_ids=["premium"])
    report = {"through": THROUGH,
              "chillingReign": rpc_cases(client, CHILLING, standard),
              "threeSet": rpc_cases(client, SETS, standard),
              "compounds": rpc_cases(client, SETS, compounds),
              "fullCache": cached(client, full_spec, True),
              "compoundCache": cached(client, compound_spec, False)}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
