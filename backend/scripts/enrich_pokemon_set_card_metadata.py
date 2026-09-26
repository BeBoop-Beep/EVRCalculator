from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.pokemon_post_scrape_card_enrichment import (
    enrich_scraped_set_card_metadata,
)


def load_backend_env() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Hydrate an already-scraped Pokemon set with Pokemon TCG API card "
            "identity, images, and canonical metadata. Dry-run by default."
        )
    )
    p.add_argument("--set", dest="set_key", required=True, help="sets.canonical_key")
    p.add_argument(
        "--pokemon-api-set-id",
        default=None,
        help="Verified provider set id override; otherwise use sets.pokemon_api_set_id/name resolution",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    load_backend_env()
    client = create_service_role_client()

    rows = list(
        client.table("sets")
        .select("id,name,canonical_key,pokemon_api_set_id")
        .eq("canonical_key", args.set_key)
        .limit(1)
        .execute().data
        or []
    )
    if not rows:
        print(json.dumps({"status": "set_not_found", "canonical_key": args.set_key}))
        return 2
    set_row = rows[0]

    card_rows = list(
        client.table("cards")
        .select("id")
        .eq("set_id", set_row["id"])
        .limit(1000)
        .execute().data
        or []
    )
    card_count = len(card_rows)
    report = enrich_scraped_set_card_metadata(
        set_id=str(set_row["id"]),
        set_name=str(set_row.get("name") or args.set_key),
        canonical_key=str(set_row.get("canonical_key") or args.set_key),
        cards_scraped=card_count,
        expected_api_set_id=(
            args.pokemon_api_set_id
            or set_row.get("pokemon_api_set_id")
        ),
        client=client,
        dry_run=not bool(args.commit),
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))

    status = str(report.get("status") or "")
    return 0 if status in {
        "already_complete",
        "dry_run",
        "enriched",
        "partial",
        "skipped_no_cards",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
