"""Validate and benchmark paginated Market Explorer constituent cache reads."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.market_explorer_query_planner import PersistentMarketExplorerCache


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    client = create_service_role_client()
    expected_rows = list((client.table("pokemon_market_explorer_query_cache")
                          .select("current_constituents,computed_through")
                          .eq("query_fingerprint", args.fingerprint).limit(1).execute()).data or [])
    expected = list(expected_rows[0]["current_constituents"])
    repository = PersistentMarketExplorerCache(client)
    items, cursor, timings, sizes = [], 0, [], []
    while True:
        started = time.perf_counter()
        page = repository.constituent_page(args.fingerprint, limit=100, after_rank=cursor)
        timings.append((time.perf_counter() - started) * 1000)
        sizes.append(len(json.dumps(page, separators=(",", ":")).encode()))
        page_items = list((page or {}).get("items") or [])
        items.extend(page_items)
        next_cursor = (page or {}).get("next_cursor")
        if next_cursor is None:
            break
        cursor = int(next_cursor)
    report = {
        "fingerprint": args.fingerprint, "exact": items == expected,
        "expectedCount": len(expected), "actualCount": len(items),
        "duplicateVariantIds": len(items) - len({row.get("cardVariantId") for row in items}),
        "pageCount": len(timings), "firstPageMs": timings[0],
        "middlePageMs": timings[len(timings) // 2], "lastPageMs": timings[-1],
        "firstPageBytes": sizes[0], "middlePageBytes": sizes[len(sizes) // 2],
        "lastPageBytes": sizes[-1], "totalBytes": sum(sizes),
        "maxPageMs": max(timings),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
