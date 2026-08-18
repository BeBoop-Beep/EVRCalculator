from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.pokemon_market_index_service import build_market_index_history, persist_index_rows, resolve_eligible_sets
from backend.domain.pokemon.market_index import CHASE_INDEX_KEY, INDEX_KEYS, MARKET_INDEX_CONTRACT_VERSION, MARKET_INDEX_METHODOLOGY_VERSION, RAW_INDEX_KEY
from backend.scripts.pokemon_snapshot_builders import get_client


def parser():
    p = argparse.ArgumentParser(description="Build chain-linked Pokemon Market index history")
    mode = p.add_mutually_exclusive_group(required=True); mode.add_argument("--dry-run", action="store_true"); mode.add_argument("--commit", action="store_true")
    p.add_argument("--market-date"); p.add_argument("--backfill", action="store_true"); p.add_argument("--from-date")
    return p


def build(client, *, market_date=None, backfill=False, from_date=None, commit=False):
    rows = build_market_index_history(client, through_date=market_date)
    if from_date: rows = [row for row in rows if row["market_date"] >= from_date]
    if market_date and not backfill: rows = [row for row in rows if row["market_date"] == market_date]
    persisted = persist_index_rows(client, rows) if commit else 0
    latest = {key: next((row for row in reversed(rows) if row["index_key"] == key), None) for key in INDEX_KEYS}
    source_fp = "|".join(str(latest[key].get("source_generation_fingerprint")) for key in INDEX_KEYS if latest[key])
    return {"contractVersion": MARKET_INDEX_CONTRACT_VERSION, "methodologyVersion": MARKET_INDEX_METHODOLOGY_VERSION,
        "indexKeys": list(INDEX_KEYS), "firstDate": min((row["market_date"] for row in rows), default=None),
        "lastDate": max((row["market_date"] for row in rows), default=None), "rowsBuilt": len(rows), "rowsPersisted": persisted,
        "eligibleSetCountCurrent": len(resolve_eligible_sets(client)),
        "rawCurrentBasketValue": latest[RAW_INDEX_KEY].get("basket_value") if latest[RAW_INDEX_KEY] else None,
        "rawCurrentCardCount": latest[RAW_INDEX_KEY].get("card_count") if latest[RAW_INDEX_KEY] else None,
        "chaseCurrentBasketValue": latest[CHASE_INDEX_KEY].get("basket_value") if latest[CHASE_INDEX_KEY] else None,
        "chaseCurrentCardCount": latest[CHASE_INDEX_KEY].get("card_count") if latest[CHASE_INDEX_KEY] else None,
        "sourceGenerationFingerprint": source_fp, "warnings": [], "errors": []}


def main():
    args = parser().parse_args()
    try: summary = build(get_client(), market_date=args.market_date, backfill=args.backfill, from_date=args.from_date, commit=args.commit)
    except Exception as exc:
        print(json.dumps({"errors": [str(exc)]}, sort_keys=True)); raise SystemExit(1) from exc
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__": main()
