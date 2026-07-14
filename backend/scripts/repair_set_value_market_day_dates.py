from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.pokemon_snapshot_builders import (
    DEFAULT_DASHBOARD_DAYS,
    DEFAULT_DASHBOARD_WINDOW,
    build_coordinated_set_market_snapshot_rows,
    get_client,
    list_pokemon_sets,
    resolve_set_row,
    upsert_row,
    upsert_rows,
)


logger = logging.getLogger("repair_set_value_market_day_dates")

MARKET_DAY_TIMEZONE = "America/Phoenix"
# Phoenix does not observe daylight saving time, so the app market day is UTC-7 year-round.
MARKET_DAY_UTC_OFFSET = timedelta(hours=-7)
SET_VALUE_SCOPES = ("standard", "hits", "top10")
DEFAULT_PAGE_SIZE = 1000
DEFAULT_CHUNK_SIZE = 200


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repair Pokemon set value daily history dates to America/Phoenix market days."
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--all", action="store_true", help="Repair all Pokemon sets")
    target_group.add_argument("--set-id", help="Set id, canonical key, or Pokemon API set id to repair")
    parser.add_argument("--start-date", help="Optional first snapshot date to refresh/delete, YYYY-MM-DD")
    parser.add_argument("--end-date", help="Optional last snapshot date to refresh/delete, YYYY-MM-DD")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Report intended work without writing")
    mode_group.add_argument("--commit", action="store_true", help="Refresh history, delete invalid rows, and rebuild dashboards")
    parser.add_argument("--days", type=int, default=DEFAULT_DASHBOARD_DAYS, help="Market dashboard history days")
    parser.add_argument("--window", default=DEFAULT_DASHBOARD_WINDOW, help="Market dashboard window key")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser


def _validate_date(value: Optional[str], label: str) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise SystemExit(f"{label} must be YYYY-MM-DD, got {value!r}") from exc


def _chunks(values: Sequence[str], size: int = DEFAULT_CHUNK_SIZE) -> Iterable[List[str]]:
    safe_size = max(1, int(size or DEFAULT_CHUNK_SIZE))
    for index in range(0, len(values), safe_size):
        yield list(values[index : index + safe_size])


def _paged_rows(client: Any, table: str, fields: str, configure_query) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        result = configure_query(client.table(table).select(fields)).range(start, start + DEFAULT_PAGE_SIZE - 1).execute()
        page = list(result.data or [])
        rows.extend(page)
        if len(page) < DEFAULT_PAGE_SIZE:
            return rows
        start += DEFAULT_PAGE_SIZE


def _parse_timestamp(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def market_day_date_key(captured_at: Any, *, timezone_name: str = MARKET_DAY_TIMEZONE) -> Optional[str]:
    parsed = _parse_timestamp(captured_at)
    if parsed is None:
        return None
    if timezone_name != MARKET_DAY_TIMEZONE:
        raise ValueError(f"Unsupported market day timezone: {timezone_name}")
    return (parsed + MARKET_DAY_UTC_OFFSET).date().isoformat()


def _near_mint_condition_id(client: Any) -> Optional[str]:
    result = client.table("conditions").select("id,name").execute()
    for row in result.data or []:
        if str(row.get("name") or "").strip().lower() == "near mint":
            return str(row.get("id"))
    return None


def _card_ids_for_set(client: Any, set_id: str) -> List[str]:
    rows = _paged_rows(client, "cards", "id", lambda query: query.eq("set_id", set_id))
    return [str(row["id"]) for row in rows if row.get("id")]


def _variant_ids_for_cards(client: Any, card_ids: Sequence[str]) -> List[str]:
    variant_ids: List[str] = []
    for card_id_chunk in _chunks(card_ids):
        rows = _paged_rows(client, "card_variants", "id", lambda query, ids=card_id_chunk: query.in_("card_id", ids))
        variant_ids.extend(str(row["id"]) for row in rows if row.get("id"))
    return variant_ids


def latest_observation_utc_for_set(client: Any, set_id: str) -> Optional[str]:
    condition_id = _near_mint_condition_id(client)
    if not condition_id:
        logger.warning("Near Mint condition not found; cannot derive latest observation date for set_id=%s", set_id)
        return None

    card_ids = _card_ids_for_set(client, set_id)
    if not card_ids:
        return None
    variant_ids = _variant_ids_for_cards(client, card_ids)
    if not variant_ids:
        return None

    latest_at: Optional[str] = None
    latest_dt: Optional[datetime] = None
    for variant_id_chunk in _chunks(variant_ids):
        result = (
            client.table("card_variant_price_observations")
            .select("captured_at")
            .in_("card_variant_id", variant_id_chunk)
            .eq("condition_id", condition_id)
            .gt("market_price", 0)
            .order("captured_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = list(result.data or [])
        if not rows:
            continue
        captured_at = rows[0].get("captured_at")
        captured_dt = _parse_timestamp(captured_at)
        if captured_dt and (latest_dt is None or captured_dt > latest_dt):
            latest_at = str(captured_at)
            latest_dt = captured_dt
    return latest_at


def _invalid_daily_rows_query(client: Any, set_id: str, cutoff_date: str, start_date: Optional[str], end_date: Optional[str]):
    query = (
        client.table("pokemon_set_value_daily_history")
        .select("id,set_id,snapshot_date,value_scope")
        .eq("set_id", set_id)
        .gt("snapshot_date", cutoff_date)
    )
    if start_date:
        query = query.gte("snapshot_date", start_date)
    if end_date:
        query = query.lte("snapshot_date", end_date)
    return query


def find_invalid_daily_rows(
    client: Any,
    *,
    set_id: str,
    cutoff_date: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> List[Dict[str, Any]]:
    if not cutoff_date:
        return []
    return list(_invalid_daily_rows_query(client, set_id, cutoff_date, start_date, end_date).execute().data or [])


def delete_invalid_daily_rows(
    client: Any,
    *,
    set_id: str,
    cutoff_date: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> int:
    if not cutoff_date:
        return 0
    stale_rows = find_invalid_daily_rows(
        client,
        set_id=set_id,
        cutoff_date=cutoff_date,
        start_date=start_date,
        end_date=end_date,
    )
    if not stale_rows:
        return 0

    query = (
        client.table("pokemon_set_value_daily_history")
        .delete()
        .eq("set_id", set_id)
        .gt("snapshot_date", cutoff_date)
    )
    if start_date:
        query = query.gte("snapshot_date", start_date)
    if end_date:
        query = query.lte("snapshot_date", end_date)
    query.execute()
    return len(stale_rows)


def refresh_set_value_history(client: Any, set_id: str, start_date: Optional[str], end_date: Optional[str]) -> int:
    result = (
        client.rpc(
            "refresh_pokemon_set_value_daily_history",
            {
                "p_set_id": set_id,
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


def rebuild_market_dashboard(client: Any, set_row: Dict[str, Any], *, days: int, window: str, commit: bool) -> str:
    cards_row, dashboard_row, top_chase_history_rows = build_coordinated_set_market_snapshot_rows(
        set_row,
        days=days,
        window=window,
        client=client,
    )
    upsert_row(
        client,
        "pokemon_set_cards_snapshot_latest",
        cards_row,
        on_conflict="set_id",
        commit=commit,
    )
    upsert_rows(
        client,
        "pokemon_set_top_chase_card_daily_history",
        top_chase_history_rows,
        on_conflict="set_id,snapshot_date,rank",
        commit=commit,
    )
    upsert_row(
        client,
        "pokemon_set_market_dashboard_snapshot_latest",
        dashboard_row,
        on_conflict="set_id,window_key",
        commit=commit,
    )
    return str(dashboard_row.get("latest_market_date") or "")


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")

    start_date = _validate_date(args.start_date, "--start-date")
    end_date = _validate_date(args.end_date, "--end-date")
    if start_date and end_date and start_date > end_date:
        raise SystemExit("--start-date must be on or before --end-date")

    client = get_client()
    set_rows = list_pokemon_sets(client) if args.all else [resolve_set_row(client, args.set_id)]
    commit = bool(args.commit)
    started = time.perf_counter()
    refreshed_rows = 0
    deleted_rows = 0
    rebuilt_dashboards = 0

    logger.info(
        "%s set value market-day repair for %s set(s), start_date=%s, end_date=%s, timezone=%s",
        "COMMIT" if commit else "DRY-RUN",
        len(set_rows),
        start_date or "earliest observation",
        end_date or "latest/local current observation",
        MARKET_DAY_TIMEZONE,
    )

    for set_row in set_rows:
        set_id = str(set_row.get("id") or "")
        if not set_id:
            continue
        label = str(set_row.get("canonical_key") or set_row.get("pokemon_api_set_id") or set_id)
        latest_utc = latest_observation_utc_for_set(client, set_id)
        latest_local_date = market_day_date_key(latest_utc)
        invalid_rows = find_invalid_daily_rows(
            client,
            set_id=set_id,
            cutoff_date=latest_local_date,
            start_date=start_date,
            end_date=end_date,
        )

        if not commit:
            logger.info(
                "Would repair %s latest_raw_utc=%s latest_local_date=%s invalid_future_rows=%s",
                label,
                latest_utc,
                latest_local_date,
                len(invalid_rows),
            )
            rebuilt_dashboards += 1
            continue

        row_count = refresh_set_value_history(client, set_id, start_date, end_date)
        refreshed_rows += row_count
        stale_deleted = delete_invalid_daily_rows(
            client,
            set_id=set_id,
            cutoff_date=latest_local_date,
            start_date=start_date,
            end_date=end_date,
        )
        deleted_rows += stale_deleted
        latest_market_date = rebuild_market_dashboard(client, set_row, days=args.days, window=args.window, commit=True)
        rebuilt_dashboards += 1
        logger.info(
            "Repaired %s refreshed_rows=%s deleted_invalid_rows=%s latest_raw_utc=%s latest_local_date=%s dashboard_latest_market_date=%s",
            label,
            row_count,
            stale_deleted,
            latest_utc,
            latest_local_date,
            latest_market_date,
        )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "Done. sets=%s refreshed_rows=%s deleted_invalid_rows=%s dashboards=%s commit=%s elapsed_ms=%s",
        len(set_rows),
        refreshed_rows,
        deleted_rows,
        rebuilt_dashboards,
        commit,
        elapsed_ms,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
