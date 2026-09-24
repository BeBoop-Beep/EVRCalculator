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
    """Returns (store, ledger, http_factory, orchestrator_kwargs). v2 = provider-window, bucket-aware quota authority."""
    from dotenv import load_dotenv

    from backend.db.clients.supabase_client import create_service_role_client
    from backend.pricing_pipeline.budget import DbBudgetLedger, SqliteBudgetLedger
    from backend.pricing_pipeline.contracts import (
        DAILY_REQUEST_LIMIT, PIPELINE_VERSION, PIPELINE_VERSION_V2, PLANNING_FRACTION, PLANNING_FRACTION_V2,
        V2_STANDARD_USABLE_CEILING, PipelineError, phoenix_day,
    )
    from backend.pricing_pipeline.ebay_credentials import load_ebay_credentials
    from backend.pricing_pipeline.store import SupabaseStore
    from backend.scripts.index_fair_value_ebay_evidence_collector import BrowseHTTP, CollectorConfig, TokenProvider

    load_dotenv(ROOT / "backend/.env", override=False)
    client = create_service_role_client()
    # One credential authority: process env -> backend/.env -> (dev only) frontend/.env.local. Nothing is printed.
    allow_frontend = not (args.no_frontend_env_fallback or os.environ.get("EVR_DISABLE_FRONTEND_ENV") == "1")

    if args.pipeline_version == "v1":
        ledger = (SqliteBudgetLedger(args.state_dir / "ebay_browse_budget.sqlite3", day=phoenix_day()) if args.budget_backend == "sqlite"
                  else DbBudgetLedger(client, day=phoenix_day()))
        config = CollectorConfig(max_requests_per_day=1000, max_requests_per_run=1000, max_pages_per_search=1)

        def http_factory_v1(led: Any) -> Any:
            return BrowseHTTP(TokenProvider(load_ebay_credentials(allow_frontend_fallback=allow_frontend).as_mapping()), config, daily_ledger=led)

        return SupabaseStore(client), ledger, http_factory_v1, {
            "pipeline_version": PIPELINE_VERSION, "request_ceiling": DAILY_REQUEST_LIMIT, "planning_fraction": PLANNING_FRACTION,
            "max_requests": args.max_requests or DAILY_REQUEST_LIMIT}

    from backend.pricing_pipeline import budget_v2
    from backend.scripts import audit_ebay_quota_and_sold_access as provider

    credentials = load_ebay_credentials(allow_frontend_fallback=allow_frontend)
    keyset = budget_v2.keyset_identity(credentials.environment, credentials.client_id)
    standard = budget_v2.PoolLedger(client, keyset, budget_v2.STANDARD)
    bulk = budget_v2.PoolLedger(client, keyset, budget_v2.BULK)
    # Callers may only LOWER the run cap: the ceiling is the DB-verified 4500-request standard pool.
    config = CollectorConfig(max_requests_per_day=V2_STANDARD_USABLE_CEILING, max_requests_per_run=V2_STANDARD_USABLE_CEILING, max_pages_per_search=1)

    def fetch_usage() -> Any:
        token = provider.fetch_token(credentials, provider.BASE_SCOPE)
        if not token["granted"]:
            return {"state": "PROVIDER_USAGE_UNAVAILABLE", "limits": []}
        return provider.usage_snapshot(token["_token"], "?api_context=buy&api_name=Browse")

    verifier = budget_v2.QuotaVerifier(client, keyset, fetch_usage)

    def quota_gate() -> None:
        # Provider analytics verify the ceiling/window; the DB ledger accounts. Fail closed if the standard pool is unverifiable.
        outcome = verifier.verify()
        if outcome["buckets"][budget_v2.STANDARD].get("mode") == "FAIL_CLOSED":
            raise PipelineError("QUOTA_UNVERIFIED", str(outcome["buckets"][budget_v2.STANDARD].get("reason")))

    def http_factory(_: Any) -> Any:
        return budget_v2.RoutedBrowseHTTP(TokenProvider(credentials.as_mapping()), config, {budget_v2.STANDARD: standard, budget_v2.BULK: bulk})

    return SupabaseStore(client), standard, http_factory, {
        "pipeline_version": PIPELINE_VERSION_V2, "request_ceiling": V2_STANDARD_USABLE_CEILING, "planning_fraction": PLANNING_FRACTION_V2,
        "max_requests": args.max_requests or V2_STANDARD_USABLE_CEILING, "quota_gate": quota_gate}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--market-date", type=date.fromisoformat, help="America/Phoenix market date (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="build the target manifest only")
    parser.add_argument("--resume", dest="resume", action="store_true", default=True, help="continue an incomplete run (default)")
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="refuse to continue an existing run")
    parser.add_argument("--max-requests", type=int, default=None, help="run cap; can only LOWER the pool ceiling (v2: 4500, v1: 1000)")
    parser.add_argument("--json", action="store_true", help="print the receipt as JSON")
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--budget-backend", choices=("db", "sqlite"), default="db")
    parser.add_argument("--pipeline-version", choices=("v2", "v1"), default="v2",
                        help="v2 = ebay_api_budget_policy_v2 provider-window budget (default); v1 = historical 1000/day ledger")
    parser.add_argument("--no-frontend-env-fallback", action="store_true",
                        help="never read frontend/.env.local (production/VM); also EVR_DISABLE_FRONTEND_ENV=1")
    parser.add_argument("--no-require-tcg-ready", action="store_true", help="skip the completed-TCG-batch gate (manual runs only)")
    args = parser.parse_args(argv)

    from backend.pricing_pipeline.contracts import EXIT_FAILED, EXIT_OK, EXIT_PARTIAL, EXIT_WAITING, PipelineError, phoenix_day
    from backend.pricing_pipeline.locking import AlreadyRunning, SingleInstance
    from backend.pricing_pipeline.orchestrator import Orchestrator

    market_date = args.market_date or phoenix_day()
    log = (lambda m: print(m, file=sys.stderr, flush=True))
    try:
        with SingleInstance(args.state_dir / "daily_multi_source_pricing.lock"):
            store, ledger, http_factory, options = build_runtime(args)
            orchestrator = Orchestrator(store, ledger, args.state_dir, http_factory=http_factory,
                                        require_tcg_ready=not args.no_require_tcg_ready, log=log, **options)
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
