"""Run exact interval/projection acceptance for one or more complete eras."""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from backend.db.clients.supabase_client import create_service_role_client

INTERVAL_RPC = "get_pokemon_market_explorer_filtered_cohort"
DAILY_RPC = "get_pokemon_market_explorer_filtered_cohort_daily"


def _paged(query_factory: Any, page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list(query_factory().range(offset, offset + page_size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size


def _set_ids(client: Any, era_ids: list[str]) -> list[str]:
    sets = _paged(lambda: client.table("sets").select("id").in_("era_id", era_ids).order("id"))
    ids = sorted(str(row["id"]) for row in sets)
    covered = _paged(lambda: client.table("pokemon_market_explorer_card_daily_coverage")
                     .select("set_id").in_("set_id", ids).order("set_id"))
    return sorted(str(row["set_id"]) for row in covered)


def _params(set_ids: list[str], **overrides: Any) -> dict[str, Any]:
    return {**{
        "p_set_ids": set_ids, "p_start_date": "2026-04-11", "p_end_date": "2026-08-31",
        "p_card_ids": None, "p_segment_ids": None, "p_pokemon_ids": None,
        "p_price_segment_ids": None, "p_release_age_cohort_ids": None, "p_top_n": None,
    }, **overrides}


def _chunked(client: Any, rpc: str, value: dict[str, Any], days: int) -> list[dict[str, Any]]:
    first = date.fromisoformat(value["p_start_date"])
    last = date.fromisoformat(value["p_end_date"])
    rows: list[dict[str, Any]] = []
    cursor, previous = first, None
    while cursor <= last:
        end = min(last, cursor + timedelta(days=days - 1))
        request = {**value, "p_start_date": previous or cursor.isoformat(), "p_end_date": end.isoformat()}
        page = list(client.rpc(rpc, request).execute().data or [])
        if previous:
            page = [row for row in page if str(row.get("market_date"))[:10] != previous]
        if page:
            rows.extend(page)
            previous = str(page[-1].get("market_date"))[:10]
        cursor = end + timedelta(days=1)
    return rows


def _timed(client: Any, rpc: str, value: dict[str, Any], samples: int = 5) -> dict[str, Any]:
    elapsed: list[float] = []
    error = None
    for _ in range(samples):
        started = time.perf_counter()
        try:
            client.rpc(rpc, value).execute()
        except Exception as exc:  # preserve the operational blocker in the artifact
            error = f"{type(exc).__name__}: {exc}"
            break
        elapsed.append((time.perf_counter() - started) * 1000)
    if not elapsed:
        return {"samplesMs": [], "error": error}
    ordered = sorted(elapsed)
    return {
        "samplesMs": elapsed, "medianMs": statistics.median(elapsed),
        "p95Ms": ordered[max(0, int(len(ordered) * .95 + .999) - 1)],
        "minMs": min(elapsed), "maxMs": max(elapsed), "error": error,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--era-id", action="append", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--chunk-days", type=int, default=3)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--skip-performance", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    client = create_service_role_client()
    set_ids = _set_ids(client, args.era_id)
    cases = {
        "full": _params(set_ids), "top10": _params(set_ids, p_top_n=10),
        "rarity": _params(set_ids, p_segment_ids=["rareHolo"]),
        "rarityTop10": _params(set_ids, p_segment_ids=["rareHolo"], p_top_n=10),
        "premium": _params(set_ids, p_price_segment_ids=["premium"]),
        "premiumTop10": _params(set_ids, p_price_segment_ids=["premium"], p_top_n=10),
        "priceSegment": _params(set_ids, p_price_segment_ids=["obtainable"]),
        "releaseAge": _params(set_ids, p_release_age_cohort_ids=["established"]),
        "pokemon": _params(set_ids, p_pokemon_ids=[25]),
        "pokemonRarity": _params(set_ids, p_pokemon_ids=[25], p_segment_ids=["rareUltra"]),
        "releasePrice": _params(set_ids, p_release_age_cohort_ids=["established"],
                                p_price_segment_ids=["premium"]),
        "compoundPremium": _params(set_ids, p_segment_ids=["rareUltra"],
                                    p_price_segment_ids=["premium"]),
    }
    if args.case:
        cases = {name: value for name, value in cases.items() if name in set(args.case)}
    def compare(item: tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        name, value = item
        worker = create_service_role_client()
        started = time.perf_counter()
        try:
            interval = _chunked(worker, INTERVAL_RPC, value, args.chunk_days)
            projection = _chunked(worker, DAILY_RPC, value, args.chunk_days)
            result = {"exact": interval == projection, "rows": len(interval),
                      "elapsedMs": (time.perf_counter() - started) * 1000}
        except Exception as exc:
            result = {"exact": False, "error": f"{type(exc).__name__}: {exc}",
                      "elapsedMs": (time.perf_counter() - started) * 1000}
        return name, result

    correctness: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(compare, item) for item in cases.items()]
        for future in as_completed(futures):
            name, result = future.result()
            correctness[name] = result
            print(json.dumps({"event": "case_complete", "name": name, **result}), flush=True)
    performance = {}
    if not args.skip_performance:
        performance = {name: _timed(client, DAILY_RPC, cases[name]) for name in
                       ("full", "top10", "rarity", "premium", "releaseAge", "pokemonRarity", "compoundPremium")
                       if name in cases}
        performance["current"] = _timed(client, INTERVAL_RPC,
                                        _params(set_ids, p_start_date="2026-08-31"))
        performance["currentTop25"] = _timed(client, INTERVAL_RPC,
                                             _params(set_ids, p_start_date="2026-08-31", p_top_n=25))
    report = {"name": args.name, "eraIds": args.era_id, "setIds": set_ids,
              "setCount": len(set_ids), "allExact": all(v.get("exact") for v in correctness.values()),
              "correctness": correctness, "performance": performance}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
