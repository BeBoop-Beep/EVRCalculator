"""Evaluate a scrape batch's completeness and repair the cohort (Phase 6).

Marks the batch complete (and stamps promoted_at) only when every expected
cohort set has a valid Near Mint observation for the market date. Otherwise
requeues the missing/invalid sets (bounded by attempt limits) and queues an
actionable alert, leaving the previous complete market date public.

Intended to run after the queue drains (also invoked automatically by the worker
when it finds no pending jobs). Safe to run repeatedly.

Usage:
    python backend/scripts/complete_scrape_batch.py                       # latest batch
    python backend/scripts/complete_scrape_batch.py --market-date 2026-07-18
    python backend/scripts/complete_scrape_batch.py --no-repair           # status only
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.db.services.scrape_batch_service import run_batch_completion_and_repair
from backend.scripts.run_pokemon_set_scrape import _load_backend_env

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Complete/repair a Pokémon scrape batch.")
    parser.add_argument("--market-date", default=None, help="Market date (YYYY-MM-DD). Defaults to latest batch.")
    parser.add_argument("--no-repair", action="store_true", help="Only evaluate completeness; do not requeue.")
    args = parser.parse_args()

    _load_backend_env()
    summary = run_batch_completion_and_repair(market_date=args.market_date, repair=not args.no_repair)
    print(json.dumps(summary, indent=2, default=str))
    # Non-zero exit when incomplete so schedulers/monitors can react.
    return 0 if summary.get("status") in ("complete", "running") else 2


if __name__ == "__main__":
    raise SystemExit(main())
