"""Daily production shadow pipeline: eBay collection -> evidence -> P4C estimates -> multi-source decisions.

One entrypoint; no manual multi-script sequencing. Cron runs this under `flock -n`; a second in-process lock also
guards it. Credentials are read from the environment/dotenv files and are never printed.

  python -m backend.scripts.run_daily_multi_source_card_pricing --json                 # normal daily run (resumes)
  python -m backend.scripts.run_daily_multi_source_card_pricing --dry-run --json       # manifest only, no eBay, no DB writes
  python -m backend.scripts.run_daily_multi_source_card_pricing --market-date 2026-09-20 --max-requests 150

Exit codes: 0 complete, 1 failed (resumable), 2 partial, 75 waiting for the TCGplayer batch (retry later), 3 already running.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def default_state_dir() -> Path:
    return Path(os.environ.get("EVR_PRICING_STATE_DIR") or ROOT / "backend/.pricing_state")


def build_runtime(args: argparse.Namespace):
    from dotenv import load_dotenv

    from backend.db.clients.supabase_client import create_service_role_client
    from backend.pricing_pipeline.budget import DbBudgetLedger, SqliteBudgetLedger
    from backend.pricing_pipeline.contracts import phoenix_day
    from backend.pricing_pipeline.store import SupabaseStore
    from backend.scripts.index_fair_value_ebay_evidence_collector import BrowseHTTP, CollectorConfig, TokenProvider, load_ebay_env

    load_dotenv(ROOT / "backend/.env", override=False)
    client = create_service_role_client()
    ledger = (SqliteBudgetLedger(args.state_dir / "ebay_browse_budget.sqlite3", day=phoenix_day()) if args.budget_backend == "sqlite"
              else DbBudgetLedger(client, day=phoenix_day()))
    config = CollectorConfig(max_requests_per_day=1000, max_requests_per_run=1000, max_pages_per_search=1)

    def http_factory(led: Any) -> Any:
        return BrowseHTTP(TokenProvider(load_ebay_env()), config, daily_ledger=led)

    return SupabaseStore(client), ledger, http_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--market-date", type=date.fromisoformat, help="America/Phoenix market date (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="build the target manifest only")
    parser.add_argument("--resume", dest="resume", action="store_true", default=True, help="continue an incomplete run (default)")
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="refuse to continue an existing run")
    parser.add_argument("--max-requests", type=int, default=1000, help="run cap; never exceeds the 1000/day shared budget")
    parser.add_argument("--json", action="store_true", help="print the receipt as JSON")
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--budget-backend", choices=("db", "sqlite"), default="db")
    parser.add_argument("--no-require-tcg-ready", action="store_true", help="skip the completed-TCG-batch gate (manual runs only)")
    args = parser.parse_args(argv)

    from backend.pricing_pipeline.contracts import EXIT_FAILED, EXIT_OK, EXIT_PARTIAL, EXIT_WAITING, PipelineError, phoenix_day
    from backend.pricing_pipeline.locking import AlreadyRunning, SingleInstance
    from backend.pricing_pipeline.orchestrator import Orchestrator

    market_date = args.market_date or phoenix_day()
    log = (lambda m: print(m, file=sys.stderr, flush=True))
    try:
        with SingleInstance(args.state_dir / "daily_multi_source_pricing.lock"):
            store, ledger, http_factory = build_runtime(args)
            orchestrator = Orchestrator(store, ledger, args.state_dir, http_factory=http_factory, max_requests=args.max_requests,
                                        require_tcg_ready=not args.no_require_tcg_ready, log=log)
            result = orchestrator.preview_targets(market_date) if args.dry_run else orchestrator.run(market_date, resume=args.resume)
            if args.dry_run:
                result = {"dry_run": True, "market_date": market_date.isoformat(), **{k: result[k] for k in (
                    "target_count", "tier_counts", "candidate_counts", "planned_capacity", "cost_per_target",
                    "remaining_requests_at_plan", "selector_fingerprint")}}
            print(json.dumps(result, indent=2, default=str) if args.json else f"OK {market_date}: {result.get('target_count')} targets")
            return EXIT_OK
    except AlreadyRunning:
        print("another daily multi-source pricing run holds the lock", file=sys.stderr)
        return 3
    except PipelineError as exc:
        payload = {"market_date": market_date.isoformat(), "failure_code": exc.code, "detail": exc.detail, "status": exc.status}
        print(json.dumps(payload) if args.json else f"{exc.status}: {exc.code} {exc.detail}", file=sys.stderr)
        return {"WAITING": EXIT_WAITING, "PARTIAL": EXIT_PARTIAL}.get(exc.status, EXIT_FAILED)
    except Exception as exc:  # noqa: BLE001 - recorded on the run row by the orchestrator; never echo secrets
        print(f"FAILED: UNEXPECTED_ERROR {type(exc).__name__}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
