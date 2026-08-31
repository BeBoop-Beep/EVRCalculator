"""Local, non-production benchmark for Effort 1H planner/cache overhead."""

from __future__ import annotations

import copy
import json
import statistics
import time
from datetime import date, timedelta

from backend.db.services.market_explorer_query_planner import (
    MarketExplorerL1Cache,
    MarketExplorerQueryPlanner,
    PreparedEquivalenceRegistry,
    PublicationGeneration,
    PublicationWatermarkCache,
    publication_scope_key,
)
from backend.domain.pokemon.market_explorer_query import normalize_query_spec, query_fingerprint


class MemoryPersistent:
    def __init__(self, row=None):
        self.row = row

    def read(self, _fingerprint):
        return copy.deepcopy(self.row)

    def claim(self, **_kwargs):
        return True

    def publish(self, **_kwargs):
        return True

    def fail(self, **_kwargs):
        return None

    def repair_generation(self, _asset):
        return 0


def representative_payload(points=140, constituents=211):
    dates = [(date(2026, 4, 11) + timedelta(days=index)).isoformat()
             for index in range(points)]
    return {
        "asOf": dates[-1], "historyStartDate": dates[0], "indexValue": 113.9,
        "trend": [[market_date, 100 + index / 10] for index, market_date in enumerate(dates)],
        "trackedValueHistory": [
            {"date": market_date, "value": 1000 + index}
            for index, market_date in enumerate(dates)
        ],
        "currentConstituents": [
            {"cardVariantId": f"variant-{index}", "marketPrice": index + 1}
            for index in range(constituents)
        ],
        "metadata": {"constituentCount": constituents, "historyPointCount": points},
        "reconciliation": {"eligibleUniverseCount": constituents},
        "scope": {"startDate": dates[0], "endDate": dates[-1]},
    }


def bench(operation, samples=100):
    timings = []
    for _ in range(samples):
        started = time.perf_counter()
        operation()
        timings.append((time.perf_counter() - started) * 1000)
    return {"medianMs": round(statistics.median(timings), 4),
            "minMs": round(min(timings), 4), "maxMs": round(max(timings), 4)}


def run():
    spec = normalize_query_spec(mode="all")
    value = representative_payload()
    empty = PreparedEquivalenceRegistry()

    prepared_registry = PreparedEquivalenceRegistry()
    prepared_registry.register(spec, lambda: value)
    prepared = bench(lambda: MarketExplorerQueryPlanner().execute(
        spec=spec, prepared=prepared_registry, persistent=MemoryPersistent(),
        canonical_through=lambda: "2026-08-28", novel_builder=lambda *_: value,
    ))

    hot = MarketExplorerL1Cache()
    generation = PublicationGeneration(value["asOf"], 0)
    hot.put(query_fingerprint(spec), generation, value)
    watermarks = PublicationWatermarkCache()
    watermarks.resolve(publication_scope_key(spec), lambda: generation)
    hot_planner = MarketExplorerQueryPlanner(l1=hot, watermarks=watermarks)
    l1 = bench(lambda: hot_planner.execute(
        spec=spec, prepared=empty, persistent=MemoryPersistent(),
        canonical_through=lambda: "2026-08-28", novel_builder=lambda *_: value,
    ))
    watermark_cache_hit = bench(lambda: watermarks.resolve(
        publication_scope_key(spec), lambda: generation,
    ))
    new_generation_l1_miss = bench(lambda: hot.get(
        query_fingerprint(spec), PublicationGeneration("2026-08-29", 0),
    ))

    through = value["asOf"]
    ready = {"status": "ready", "computed_through": through, "series_payload": value}
    l2 = bench(lambda: MarketExplorerQueryPlanner().execute(
        spec=spec, prepared=empty, persistent=MemoryPersistent(ready),
        canonical_through=lambda: through, novel_builder=lambda *_: value,
    ))

    old = copy.deepcopy(value)
    old["asOf"] = old["trend"][-2][0]
    old["trend"] = old["trend"][:-1]
    old["trackedValueHistory"] = old["trackedValueHistory"][:-1]
    stale = {"status": "ready", "computed_through": old["asOf"], "series_payload": old}
    incremental = bench(lambda: MarketExplorerQueryPlanner().execute(
        spec=spec, prepared=empty, persistent=MemoryPersistent(stale),
        canonical_through=lambda: through, novel_builder=lambda *_: value,
    ))

    novel_overhead = bench(lambda: MarketExplorerQueryPlanner().execute(
        spec=spec, prepared=empty, persistent=MemoryPersistent(),
        canonical_through=lambda: through, novel_builder=lambda *_: value,
    ))

    encoded = json.dumps(value, separators=(",", ":")).encode()
    point_rows = [{"date": row[0], "value": row[1]} for row in value["trend"]]
    return {
        "historyPoints": len(value["trend"]), "payloadBytes": len(encoded),
        "jsonParse": bench(lambda: json.loads(encoded), 300),
        "childRowsMaterialize": bench(lambda: [dict(row) for row in point_rows], 300),
        "prepared": prepared, "l1": l1,
        "watermarkCacheHit": watermark_cache_hit,
        "newGenerationL1Miss": new_generation_l1_miss,
        "l2RepositorySimulated": l2,
        "incrementalMergeSimulated": incremental, "novelPlannerOverhead": novel_overhead,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
