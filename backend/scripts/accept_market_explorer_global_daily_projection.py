"""Sampled oracle/parity acceptance for the global Market Explorer daily
projection, once ``pokemon_market_explorer_card_daily_states`` covers the
full 165-set corrected authority.

This generalizes the exact ten-set comparison pattern in
``accept_market_explorer_ten_set_projection.py`` to the full corpus: it is
NOT an exhaustive full-history diff (statement-timeout bounded, same as the
ten-set script), it is a sampled correctness + timing harness intended to
run once Prompt 4's publication has actually executed against production.

Running this script performs ONLY read-only RPC calls (``client.rpc(...)``)
against the two comparison functions already used elsewhere in this
project -- ``get_pokemon_market_explorer_filtered_cohort`` (interval-path
oracle) and ``get_pokemon_market_explorer_filtered_cohort_daily`` (the
serving projection path) -- it performs no writes and is exempt from the
--dry-run/--commit gating used by the write scripts in this project.

Scope selection:
  - "global": every tracked set id (``resolve_tracked_set_ids``), covering
    Global All Raw Cards, Global Top 10, Global rareHolo, Global Premium.
  - "era": one representative set id per requested era id, covering
    representative per-era All Raw + Top 10.

Planner-path verification: before each RPC comparison this script calls the
SAME production mechanism the planner uses to decide projection-vs-interval
-- ``daily_projection_covers`` in
``backend.db.services.pokemon_market_explorer_query_service`` -- and reports
whether the scope was fully covered (projection path expected) or not
(interval fallback expected), rather than inventing a new coverage check.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Sequence

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.pokemon_market_explorer_query_service import (
    daily_projection_covers,
    resolve_tracked_set_ids,
)

INTERVAL_RPC = "get_pokemon_market_explorer_filtered_cohort"
DAILY_RPC = "get_pokemon_market_explorer_filtered_cohort_daily"
CHUNK_DAYS = 6  # matches the ten-set script's bounded statement-timeout window


def params(set_ids: Sequence[str], *, start_date: str, end_date: str, **overrides: Any) -> dict:
    return {
        "p_set_ids": list(set_ids), "p_start_date": start_date, "p_end_date": end_date,
        "p_card_ids": None, "p_segment_ids": None, "p_pokemon_ids": None,
        "p_price_segment_ids": None, "p_release_age_cohort_ids": None, "p_top_n": None,
        **overrides,
    }


def chunked(client: Any, rpc: str, value: dict) -> list[dict]:
    first, last = date.fromisoformat(value["p_start_date"]), date.fromisoformat(value["p_end_date"])
    rows: list[dict] = []
    cursor, previous = first, None
    while cursor <= last:
        end = min(last, cursor + timedelta(days=CHUNK_DAYS))
        request = {**value, "p_start_date": previous or cursor.isoformat(), "p_end_date": end.isoformat()}
        page = list(client.rpc(rpc, request).execute().data or [])
        if previous:
            page = [row for row in page if str(row.get("market_date"))[:10] != previous]
        if page:
            rows.extend(page)
            previous = str(page[-1].get("market_date"))[:10]
        cursor = end + timedelta(days=1)
    return rows


def build_cases(set_ids: Sequence[str], *, start_date: str, end_date: str) -> dict[str, dict]:
    return {
        "allRaw": params(set_ids, start_date=start_date, end_date=end_date),
        "top10": params(set_ids, start_date=start_date, end_date=end_date, p_top_n=10),
        "rareHolo": params(set_ids, start_date=start_date, end_date=end_date, p_segment_ids=["rareHolo"]),
        "premium": params(set_ids, start_date=start_date, end_date=end_date, p_price_segment_ids=["premium"]),
    }


def run_acceptance(
    client: Any,
    *,
    start_date: str,
    end_date: str,
    era_representatives: dict[str, str] | None = None,
    perf_samples: int = 5,
) -> dict[str, Any]:
    era_representatives = era_representatives or {}
    global_set_ids = resolve_tracked_set_ids(client)

    coverage: dict[str, Any] = {
        "global": daily_projection_covers(client, global_set_ids, start_date=start_date, end_date=end_date),
    }
    scopes: dict[str, dict] = {"global": build_cases(global_set_ids, start_date=start_date, end_date=end_date)}

    for era_id, set_id in era_representatives.items():
        coverage[f"era:{era_id}"] = daily_projection_covers(
            client, [set_id], start_date=start_date, end_date=end_date)
        scopes[f"era:{era_id}"] = {
            "allRaw": params([set_id], start_date=start_date, end_date=end_date),
            "top10": params([set_id], start_date=start_date, end_date=end_date, p_top_n=10),
        }

    correctness: dict[str, bool] = {}
    for scope_name, cases in scopes.items():
        for case_name, value in cases.items():
            key = f"{scope_name}.{case_name}"
            correctness[key] = (chunked(client, INTERVAL_RPC, value)
                                 == chunked(client, DAILY_RPC, value))

    performance: dict[str, Any] = {}
    for scope_name, cases in scopes.items():
        for case_name, value in cases.items():
            key = f"{scope_name}.{case_name}"
            samples = []
            for _ in range(perf_samples):
                started = time.perf_counter()
                client.rpc(DAILY_RPC, value).execute()
                samples.append((time.perf_counter() - started) * 1000)
            performance[key] = {
                "medianMs": statistics.median(samples), "p95Ms": max(samples),
                "minMs": min(samples), "maxMs": max(samples),
            }

    return {
        "startDate": start_date, "endDate": end_date,
        "plannerPathCoverage": coverage,
        "expectedPath": {k: ("projection" if v else "interval_fallback") for k, v in coverage.items()},
        "correctness": correctness,
        "allExact": all(correctness.values()),
        "performance": performance,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--era-representative", action="append", default=[],
                        metavar="ERA_ID:SET_ID", help="Repeatable era-id:set-id pair.")
    parser.add_argument("--perf-samples", type=int, default=5)
    parser.add_argument("--output", default="artifacts/market_explorer_acceptance/global_daily_projection_acceptance.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    era_representatives = {}
    for entry in args.era_representative:
        era_id, _, set_id = entry.partition(":")
        if not era_id or not set_id:
            raise SystemExit(f"invalid --era-representative {entry!r}, expected ERA_ID:SET_ID")
        era_representatives[era_id] = set_id

    report = run_acceptance(
        create_service_role_client(),
        start_date=args.start_date.isoformat(), end_date=args.end_date.isoformat(),
        era_representatives=era_representatives, perf_samples=args.perf_samples,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["allExact"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
