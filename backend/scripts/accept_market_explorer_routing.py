"""Exercise production planner routing and L2/L1 reuse for the ten-set scope."""
from __future__ import annotations

import json
from pathlib import Path

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.market_explorer_query_planner import (
    MarketExplorerQueryPlanner, PersistentMarketExplorerCache,
    PreparedEquivalenceRegistry, resolve_canonical_through,
)
from backend.db.services.pokemon_market_explorer_query_service import run_market_explorer_query
from backend.domain.pokemon.market_explorer_query import normalize_query_spec
from backend.scripts.accept_market_explorer_ten_set_projection import SETS


def main() -> None:
    client = create_service_role_client()
    spec = normalize_query_spec(mode="all", set_ids=SETS)
    prepared = PreparedEquivalenceRegistry()
    persistent = PersistentMarketExplorerCache(client)
    def build(previous, through):
        return run_market_explorer_query(client, mode=spec["mode"], era_ids=spec["eraIds"],
            set_ids=spec["setIds"], segment_ids=spec["segmentIds"], pokemon_ids=spec["pokemonIds"],
            price_segment_ids=spec["priceSegmentIds"], release_age_cohort_ids=spec["releaseAgeCohortIds"],
            top_n=spec["topN"], start_date=previous or "1999-01-01", end_date=through)
    kwargs = dict(spec=spec, prepared=prepared, persistent=persistent,
                  canonical_through=lambda: resolve_canonical_through(client, spec), novel_builder=build)
    first = MarketExplorerQueryPlanner().execute(**kwargs)
    warm = MarketExplorerQueryPlanner()
    second = warm.execute(**kwargs)
    third = warm.execute(**kwargs)
    report = {"sources": [first.execution_source, second.execution_source, third.execution_source],
              "elapsedMs": [first.elapsed_ms, second.elapsed_ms, third.elapsed_ms],
              "identical": first.payload == second.payload == third.payload,
              "payloadBytes": len(json.dumps(first.payload, separators=(",", ":")).encode())}
    path = Path("artifacts/market_explorer_acceptance/20260831_effort1k_routing.json")
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
