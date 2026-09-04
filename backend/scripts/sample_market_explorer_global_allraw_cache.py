"""Sample L2/L1 timings + verify slimming/detail for the already-built Global All Raw cache."""
import json, time
from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.market_explorer_query_planner import (
    MarketExplorerL1Cache, MarketExplorerQueryPlanner, PersistentMarketExplorerCache,
    PreparedEquivalenceRegistry,
)
from backend.db.services.pokemon_market_explorer_query_service import run_market_explorer_query
from backend.domain.pokemon.market_explorer_query import normalize_query_spec, query_fingerprint

PINNED_THROUGH = "2026-09-02"
START = "2026-04-07"


def builder(client, spec):
    def build(previous, through):
        return run_market_explorer_query(
            client, mode=spec["mode"], era_ids=spec["eraIds"], set_ids=spec["setIds"],
            segment_ids=spec["segmentIds"], pokemon_ids=spec["pokemonIds"],
            price_segment_ids=spec["priceSegmentIds"],
            release_age_cohort_ids=spec["releaseAgeCohortIds"], top_n=spec["topN"],
            start_date=previous or START, end_date=through)
    return build


def execute(client, planner, spec, summary=False):
    return planner.execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=PersistentMarketExplorerCache(client, build_lease_seconds=300),
        canonical_through=lambda: PINNED_THROUGH,
        novel_builder=builder(client, spec), summary=summary)


def main():
    spec = normalize_query_spec(mode="all", asset="cards", era_ids=[], set_ids=[], top_n=None)
    fingerprint = query_fingerprint(spec)

    l2_times, l2_sources = [], []
    for _ in range(2):
        client = create_service_role_client()
        t0 = time.perf_counter()
        result = execute(client, MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache()), spec, summary=True)
        l2_times.append((time.perf_counter() - t0) * 1000)
        l2_sources.append(result.execution_source)

    hot_client = create_service_role_client()
    hot_planner = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache())
    execute(hot_client, hot_planner, spec, summary=True)
    l1_times, l1_sources = [], []
    for _ in range(2):
        t0 = time.perf_counter()
        result = execute(hot_client, hot_planner, spec, summary=True)
        l1_times.append((time.perf_counter() - t0) * 1000)
        l1_sources.append(result.execution_source)

    payload = result.payload
    slimming = {
        "currentConstituents_absent": "currentConstituents" not in payload,
        "membershipByDate_absent": "membershipByDate" not in payload,
        "payload_keys": sorted(payload.keys()),
    }

    control = create_service_role_client()
    detail_rows = (control.table("pokemon_market_explorer_query_cache_constituents")
                   .select("card_variant_id", count="exact")
                   .eq("query_fingerprint", fingerprint).limit(1).execute())
    total_detail = detail_rows.count

    page1 = (control.table("pokemon_market_explorer_query_cache_constituents")
              .select("card_variant_id,rank").eq("query_fingerprint", fingerprint)
              .order("rank").range(0, 4).execute()).data
    page2 = (control.table("pokemon_market_explorer_query_cache_constituents")
              .select("card_variant_id,rank").eq("query_fingerprint", fingerprint)
              .order("rank").range(1000, 1004).execute()).data

    unique_check = (control.table("pokemon_market_explorer_query_cache_constituents")
                     .select("card_variant_id").eq("query_fingerprint", fingerprint).execute()).data
    unique_ids = {r["card_variant_id"] for r in unique_check}

    ledger = (control.table("pokemon_market_explorer_variant_merge_ledger")
              .select("predecessor_variant_id").execute()).data
    retired_ids = {r["predecessor_variant_id"] for r in ledger}
    retired_in_detail = unique_ids & retired_ids

    print(json.dumps({
        "fingerprint": fingerprint,
        "l2": {"samplesMs": l2_times, "sources": l2_sources},
        "l1": {"samplesMs": l1_times, "sources": l1_sources},
        "slimming": slimming,
        "detail_total_count": total_detail,
        "unique_ids_count": len(unique_ids),
        "retired_ids_in_detail_count": len(retired_in_detail),
        "page1": page1,
        "page2": page2,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
