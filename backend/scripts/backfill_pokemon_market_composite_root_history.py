"""Dry-run by default; bounded composite-root history backfill with --commit."""

from __future__ import annotations

import argparse
import json

from backend.db.clients.supabase_client import supabase
from backend.db.services.pokemon_market_historical_root_value import execute_historical_root_backfill


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set-id", action="append", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    result = execute_historical_root_backfill(
        supabase, args.set_id, args.start_date, args.end_date, commit=args.commit,
    )
    print(json.dumps({"commit": args.commit, "rows": result}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
