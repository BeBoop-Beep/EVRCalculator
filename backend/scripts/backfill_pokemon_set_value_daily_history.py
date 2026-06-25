from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.clients.supabase_client import create_service_role_client


logger = logging.getLogger("backfill_pokemon_set_value_daily_history")


@dataclass(frozen=True)
class SetTarget:
    id: str
    name: str
    canonical_key: Optional[str]
    pokemon_api_set_id: Optional[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill scoped daily Pokemon set value history from card price observations."
    )
    parser.add_argument(
        "--set",
        dest="set_key",
        help="Optional set id, canonical key, or Pokemon API set id. Defaults to all sets.",
    )
    parser.add_argument(
        "--set-id",
        dest="set_key",
        help="Alias for --set. Accepts a set id, canonical key, or Pokemon API set id.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of sets to refresh before printing batch progress. Default: 10.",
    )
    parser.add_argument(
        "--start-date",
        help="Optional first snapshot date to refresh, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        help="Optional last snapshot date to refresh, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Write rows by invoking refresh_pokemon_set_value_daily_history. Omit for dry-run.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser.parse_args()


def validate_date(value: Optional[str], label: str) -> Optional[str]:
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise SystemExit(f"{label} must be YYYY-MM-DD, got {value!r}") from exc


def fetch_all_sets(client: Any) -> List[SetTarget]:
    rows: List[Dict[str, Any]] = []
    page_size = 1000
    start = 0

    while True:
        result = (
            client.table("sets")
            .select("id,name,canonical_key,pokemon_api_set_id")
            .order("name", desc=False)
            .range(start, start + page_size - 1)
            .execute()
        )
        page = list(result.data or [])
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size

    return [row_to_target(row) for row in rows if row.get("id")]


def resolve_set(client: Any, set_key: str) -> SetTarget:
    cleaned = str(set_key or "").strip()
    if not cleaned:
        raise SystemExit("--set cannot be blank")

    lookup_fields = ["canonical_key", "pokemon_api_set_id"]
    try:
        UUID(cleaned)
        lookup_fields.insert(0, "id")
    except ValueError:
        pass

    for field in lookup_fields:
        result = (
            client.table("sets")
            .select("id,name,canonical_key,pokemon_api_set_id")
            .eq(field, cleaned)
            .limit(1)
            .execute()
        )
        if result.data:
            return row_to_target(result.data[0])

    raise SystemExit(f"No Pokemon set found for {cleaned!r}")


def row_to_target(row: Dict[str, Any]) -> SetTarget:
    return SetTarget(
        id=str(row.get("id")),
        name=str(row.get("name") or "Unknown set"),
        canonical_key=str(row.get("canonical_key") or "") or None,
        pokemon_api_set_id=str(row.get("pokemon_api_set_id") or "") or None,
    )


def chunks(values: List[SetTarget], size: int) -> Iterable[List[SetTarget]]:
    chunk_size = max(1, size)
    for index in range(0, len(values), chunk_size):
        yield values[index : index + chunk_size]


def refresh_set(client: Any, target: SetTarget, start_date: Optional[str], end_date: Optional[str]) -> int:
    result = (
        client.rpc(
            "refresh_pokemon_set_value_daily_history",
            {
                "p_set_id": target.id,
                "p_start_date": start_date,
                "p_end_date": end_date,
            },
        )
        .execute()
    )
    try:
        return int(result.data or 0)
    except (TypeError, ValueError):
        return 0


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")

    start_date = validate_date(args.start_date, "--start-date")
    end_date = validate_date(args.end_date, "--end-date")
    if start_date and end_date and start_date > end_date:
        raise SystemExit("--start-date must be on or before --end-date")

    client = create_service_role_client()
    targets = [resolve_set(client, args.set_key)] if args.set_key else fetch_all_sets(client)

    if not targets:
        logger.info("No sets found.")
        return 0

    mode = "COMMIT" if args.commit else "DRY-RUN"
    logger.info(
        "%s scoped set value history refresh for %s set(s), start_date=%s, end_date=%s",
        mode,
        len(targets),
        start_date or "earliest observation",
        end_date or "latest observation",
    )

    total_rows = 0
    started = time.perf_counter()
    processed = 0

    for batch_index, batch in enumerate(chunks(targets, args.batch_size), start=1):
        logger.info("Batch %s: %s set(s)", batch_index, len(batch))
        for target in batch:
            label = target.canonical_key or target.pokemon_api_set_id or target.id
            if not args.commit:
                logger.info("Would refresh %s (%s)", target.name, label)
                processed += 1
                continue

            row_count = refresh_set(client, target, start_date, end_date)
            total_rows += row_count
            processed += 1
            logger.info("Refreshed %s (%s): %s scoped row(s) upserted", target.name, label, row_count)

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "Done. processed_sets=%s scoped_rows_upserted=%s elapsed_ms=%s commit=%s",
        processed,
        total_rows,
        elapsed_ms,
        args.commit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
