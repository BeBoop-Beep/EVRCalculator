"""CLI for the shadow-only daily eBay Browse evidence collector.

Examples:
    python backend/scripts/run_index_fair_value_ebay_daily.py --dry-run
    python backend/scripts/run_index_fair_value_ebay_daily.py --run --cohort d1_70
    python backend/scripts/run_index_fair_value_ebay_daily.py --run --resume <run-id>

Dry-run performs zero eBay API calls: it only resolves the cohort, builds
queries, and writes a planning manifest. --live-smoke is the only flag that
is allowed to make a small number of bounded, real Browse requests.
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from backend.scripts.index_fair_value_ebay_evidence_collector import (
    ARTIFACTS_DIR,
    RUNS_DIR,
    BrowseHTTP,
    Collector,
    CollectorConfig,
    RunState,
    TokenProvider,
    cohort_fingerprint,
    generate_queries,
    load_ebay_env,
    select_cohort,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan only; zero network calls.")
    mode.add_argument("--run", action="store_true", help="Execute the collector against eBay Browse.")
    mode.add_argument("--live-smoke", action="store_true", help="Tightly bounded live validation (<=10 requests).")
    parser.add_argument("--cohort", default="d1_70")
    parser.add_argument("--target-file")
    parser.add_argument("--resume")
    parser.add_argument("--max-requests", type=int, default=1000, help="Max Browse requests for this run (application budget).")
    parser.add_argument("--max-pages-per-search", type=int, default=3)
    parser.add_argument("--max-listings-per-target", type=int, default=200)
    parser.add_argument("--no-match", action="store_true", help="Skip running the matcher; capture raw evidence only.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON summary to stdout.")
    return parser


def _config_from_args(args: argparse.Namespace) -> CollectorConfig:
    if args.live_smoke:
        return CollectorConfig(
            max_requests_per_day=1000,
            max_requests_per_run=10,
            max_pages_per_search=2,
            max_listings_per_target=200,
            run_matcher=not args.no_match,
        )
    return CollectorConfig(
        max_requests_per_day=1000,
        max_requests_per_run=args.max_requests,
        max_pages_per_search=args.max_pages_per_search,
        max_listings_per_target=args.max_listings_per_target,
        run_matcher=not args.no_match,
    )


def main(argv: list[str] | None = None) -> dict:
    args = build_arg_parser().parse_args(argv)
    cards = select_cohort(name=args.cohort, target_file=args.target_file)
    if args.live_smoke:
        cards = cards[:2]

    if args.dry_run:
        plan = {
            "mode": "dry_run",
            "cohort": args.cohort,
            "cohort_size": len(cards),
            "cohort_fingerprint": cohort_fingerprint(cards),
            "targets": [
                {"canonical_card_id": c["canonical_card_id"], "queries": generate_queries(c)} for c in cards
            ],
            "ebay_calls_made": 0,
        }
        if args.json:
            print(json.dumps(plan, indent=2, ensure_ascii=False))
        return plan

    config = _config_from_args(args)
    if args.resume:
        state = RunState.load(args.resume)
    else:
        run_id = uuid.uuid4().hex
        state = RunState.new(run_id, cards, config)
        state.save()

    env = load_ebay_env()
    tokens = TokenProvider(env)
    http = BrowseHTTP(tokens, config)
    collector = Collector(http, config)
    state = collector.run(state, cards)
    state.save()

    summary = {
        "mode": "live_smoke" if args.live_smoke else "run",
        "run_id": state.run_id,
        "completed": state.completed,
        "requests_attempted": state.requests_attempted,
        "requests_successful": state.requests_successful,
        "requests_failed": state.requests_failed,
        "retries": state.retries,
        "targets_completed": sum(1 for t in state.targets.values() if t.get("status") == "completed"),
        "targets_deferred": sum(1 for t in state.targets.values() if t.get("status") == "deferred"),
        "raw_evidence_path": str(state.raw_evidence_path()),
        "match_results_path": str(state.match_results_path()),
    }
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()
