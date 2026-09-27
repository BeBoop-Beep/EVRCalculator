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
    parser.add_argument("--normalize-provenance", action="store_true")
    parser.add_argument("--repair-conflicting-generic", action="store_true")
    parser.add_argument("--freeze-constituents", action="store_true",
                        help="persist the exact in-memory leaf roster (requires --commit)")
    args = parser.parse_args()
    if args.repair_conflicting_generic and not args.normalize_provenance:
        parser.error("--repair-conflicting-generic requires --normalize-provenance")
    if args.freeze_constituents and not args.commit:
        parser.error("--freeze-constituents requires --commit (dry-run performs zero writes)")
    result = execute_historical_root_backfill(
        supabase, args.set_id, args.start_date, args.end_date, commit=args.commit,
        normalize_provenance=args.normalize_provenance,
        repair_conflicting_generic=args.repair_conflicting_generic,
        freeze_constituents=args.freeze_constituents,
    )
    result = [{k: v for k, v in row.items() if k != "frozen_items"} for row in result]
    print(json.dumps({"commit": args.commit, "rows": result}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
