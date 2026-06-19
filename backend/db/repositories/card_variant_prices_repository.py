import base64
import json
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple, Set

from postgrest.exceptions import APIError
from supabase import create_client

from ..clients.supabase_client import SUPABASE_URL, SUPABASE_KEY
import time


def _jwt_role(key: str) -> str:
    """Decode the JWT payload segment to extract the 'role' claim (service_role vs anon)."""
    try:
        parts = key.split(".")
        if len(parts) == 3:
            payload = parts[1]
            payload += "=" * (-len(payload) % 4)  # fix padding
            decoded = json.loads(base64.b64decode(payload))
            return decoded.get("role", "unknown")
    except Exception:
        pass
    return "unknown"


logger = logging.getLogger(__name__)


_LATEST_CARD_MARKET_VIEW = "card_market_usd_latest_by_condition"
_LATEST_CARD_MARKET_IN_CHUNK_SIZE = 500


def _parse_captured_at(value: Any) -> datetime:
    """Parse captured_at value into a timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        # Handle both ISO with Z and naive ISO strings.
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = datetime.now(timezone.utc)

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_price_row(price_row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a price row before insert."""
    normalized = dict(price_row)
    captured_at_dt = _parse_captured_at(normalized.get("captured_at"))

    normalized["captured_at"] = captured_at_dt.isoformat()
    normalized["source"] = normalized.get("source") or "UNKNOWN"
    normalized["currency"] = normalized.get("currency") or "USD"

    return normalized


def _normalize_market_price(value: Any) -> Optional[str]:
    """Convert market_price into a comparable decimal string."""
    if value is None:
        return None
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def _identity_key(price_row: Dict[str, Any]) -> str:
    """Build entity+source+day key (no price fields) to identify same-day rows."""
    captured_at_dt = _parse_captured_at(price_row.get("captured_at"))
    return "|".join(
        [
            str(price_row.get("card_variant_id")),
            str(price_row.get("condition_id")),
            str(price_row.get("source") or "UNKNOWN"),
            captured_at_dt.date().isoformat(),
        ]
    )


def _prices_match(incoming: Dict[str, Any], existing: Dict[str, Any]) -> bool:
    """Return True only if all relevant price fields (market_price, high_price, low_price) are identical."""
    for field in ("market_price", "high_price", "low_price"):
        if _normalize_market_price(incoming.get(field)) != _normalize_market_price(existing.get(field)):
            return False
    return True


def _refresh_pokemon_set_value_history_for_price_rows(price_rows: List[Dict[str, Any]]) -> None:
    changed_rows = [row for row in price_rows if row.get("card_variant_id")]
    if not changed_rows:
        return

    variant_ids = sorted({str(row.get("card_variant_id")) for row in changed_rows if row.get("card_variant_id")})
    captured_dates = [
        _parse_captured_at(row.get("captured_at")).date().isoformat()
        for row in changed_rows
        if row.get("captured_at")
    ]
    start_date = min(captured_dates) if captured_dates else datetime.now(timezone.utc).date().isoformat()

    try:
        refresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        refresh_client.rpc(
            "refresh_pokemon_set_value_daily_history_for_variants",
            {
                "p_card_variant_ids": variant_ids,
                "p_start_date": start_date,
            },
        ).execute()
    except Exception as exc:
        logger.warning(
            "Unable to refresh pokemon_set_value_daily_history for %s changed card variant price row(s): %s",
            len(changed_rows),
            exc,
        )


def _fetch_existing_same_day_observations(
    normalized_rows: List[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """
    Fetch existing same-day rows keyed by identity_key.
    Returns (Dict[identity_key -> existing_row], query_count).
    Each existing_row contains: id, market_price, high_price, low_price.
    """
    if not normalized_rows:
        return {}, 0

    rows_by_day: Dict[str, List[Dict[str, Any]]] = {}
    for row in normalized_rows:
        day_key = _parse_captured_at(row.get("captured_at")).date().isoformat()
        rows_by_day.setdefault(day_key, []).append(row)

    existing_by_identity: Dict[str, Dict[str, Any]] = {}
    query_count = 0

    for day_key, day_rows in rows_by_day.items():
        day_start = f"{day_key}T00:00:00+00:00"
        day_end = f"{day_key}T23:59:59.999999+00:00"

        variant_ids = sorted({row.get("card_variant_id") for row in day_rows if row.get("card_variant_id") is not None})
        condition_ids = sorted({row.get("condition_id") for row in day_rows if row.get("condition_id") is not None})
        sources = sorted({(row.get("source") or "UNKNOWN") for row in day_rows})

        if not variant_ids or not condition_ids:
            continue

        fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        query_count += 1
        res = (
            fresh_client.table("card_variant_price_observations")
            .select("id, card_variant_id, condition_id, source, captured_at, market_price, high_price, low_price")
            .in_("card_variant_id", variant_ids)
            .in_("condition_id", condition_ids)
            .in_("source", sources)
            .gte("captured_at", day_start)
            .lte("captured_at", day_end)
            .execute()
        )

        existing_rows = res.data if res and res.data else []
        for existing in existing_rows:
            key = _identity_key(existing)
            existing_by_identity[key] = existing

    return existing_by_identity, query_count


def insert_card_variant_price(price_row: Dict[str, Any]) -> int:
    """
    Insert a price row into `card_variant_price_observations`.
    
    Args:
        price_row: Should include card_variant_id, condition_id, market_price, 
                   currency (optional), source, captured_at, high_price (optional), low_price (optional)
                   
    Returns:
        The id of the newly inserted price record
        
    Raises:
        RuntimeError: If insertion fails
    """
    normalized_row = _normalize_price_row(price_row)
    
    # Retry mechanism for schema cache issues
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Create a fresh client for each attempt to avoid schema cache issues
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = (
                fresh_client.table("card_variant_price_observations")
                .insert(normalized_row)
                .execute()
            )
            
            if res is None:
                raise RuntimeError("Insert card variant price returned no response object")
            
            # Success!
            inserted = res.data
            if not inserted:
                raise RuntimeError("Insert returned no data")

            _refresh_pokemon_set_value_history_for_price_rows([normalized_row])
            return inserted[0]["id"]
        
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            
            # Check if it's a schema cache error
            if "schema cache" in error_msg.lower():
                print(f"[WARN]  Schema cache error on attempt {attempt + 1}/{max_retries}, retrying...")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait before retry
                    continue
            else:
                # Not a schema cache error, fail immediately
                print(f"[DEBUG] API Error: {error_msg}")
                raise RuntimeError(f"Failed to insert card variant price: {error_msg}")
        
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                print(f"[WARN]  Retrying after error: {e}")
                time.sleep(1)
                continue
            raise
    
    raise RuntimeError(f"Failed to insert price after {max_retries} retries: {last_error}")



def get_latest_price(card_variant_id: int, condition_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the most recent price record for a card variant and condition.
    
    Args:
        card_variant_id: The ID of the card variant
        condition_id: The ID of the condition
        
    Returns:
        The most recent price record, or None if not found
    """
    key_role = _jwt_role(SUPABASE_KEY)
    logger.warning(
        "[portfolio-debug] card price lookup start | url=%s | key_role=%s | card_variant_id=%s | condition_id=%s | source=card_market_usd_latest_by_condition",
        SUPABASE_URL,
        key_role,
        card_variant_id,
        condition_id,
    )
    fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    res = (
        fresh_client.table(_LATEST_CARD_MARKET_VIEW)
        .select("*")
        .eq("variant_id", card_variant_id)
        .eq("condition_id", condition_id)
        .maybe_single()
        .execute()
    )
    row = res.data if res and res.data else None
    logger.warning(
        "[portfolio-debug] card price lookup result | card_variant_id=%s | condition_id=%s | found=%s | market_price=%s | row_keys=%s | raw_res_data=%s | raw_res_count=%s",
        card_variant_id,
        condition_id,
        bool(row),
        row.get("market_price") if isinstance(row, dict) else None,
        sorted(row.keys()) if isinstance(row, dict) else None,
        res.data if res else "NO_RES",
        getattr(res, "count", "N/A"),
    )
    return row


def _normalize_variant_ids(values: List[Any]) -> Tuple[List[str], int]:
    cleaned: List[str] = []
    dropped = 0
    seen: Set[str] = set()

    for raw in values:
        if raw is None:
            dropped += 1
            continue
        token = str(raw).strip()
        if not token:
            dropped += 1
            continue
        if token in seen:
            continue
        seen.add(token)
        cleaned.append(token)

    return cleaned, dropped


def _chunk_list(values: List[str], size: int) -> List[List[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def get_latest_prices_for_variants(variant_ids: List[Any], condition_id: Any) -> List[Dict[str, Any]]:
    """Return latest market rows from view for variant IDs at a single condition."""
    if not variant_ids:
        return []

    normalized_variant_ids, dropped_count = _normalize_variant_ids(variant_ids)
    normalized_condition_id = None if condition_id is None else str(condition_id).strip()

    if not normalized_variant_ids or not normalized_condition_id:
        logger.warning(
            "[DB_CARD_PRICE_QUERY] checkpoint=preflight-empty table=%s variant_count_raw=%s variant_count_normalized=%s dropped_variant_ids=%s condition_id=%r condition_type=%s",
            _LATEST_CARD_MARKET_VIEW,
            len(variant_ids),
            len(normalized_variant_ids),
            dropped_count,
            condition_id,
            type(condition_id).__name__,
        )
        return []

    chunk_size = _LATEST_CARD_MARKET_IN_CHUNK_SIZE
    chunks = _chunk_list(normalized_variant_ids, chunk_size)

    sample_ids = normalized_variant_ids[:5]
    sample_types = sorted({type(v).__name__ for v in variant_ids[:10]})
    logger.warning(
        "[DB_CARD_PRICE_QUERY] checkpoint=before-execute table=%s variant_count_raw=%s variant_count_normalized=%s chunk_count=%s chunk_size=%s dropped_variant_ids=%s sample_variant_ids=%s sample_variant_types=%s condition_id=%s condition_type=%s",
        _LATEST_CARD_MARKET_VIEW,
        len(variant_ids),
        len(normalized_variant_ids),
        len(chunks),
        chunk_size,
        dropped_count,
        sample_ids,
        sample_types,
        normalized_condition_id,
        type(condition_id).__name__,
    )

    fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    results: List[Dict[str, Any]] = []

    for idx, chunk in enumerate(chunks, start=1):
        try:
            res = (
                fresh_client.table(_LATEST_CARD_MARKET_VIEW)
                .select("*")
                .in_("variant_id", chunk)
                .eq("condition_id", normalized_condition_id)
                .execute()
            )
        except APIError as exc:
            logger.error(
                "[DB_CARD_PRICE_QUERY] checkpoint=chunk-failed table=%s chunk_index=%s chunk_count=%s chunk_size=%s condition_id=%s error=%s",
                _LATEST_CARD_MARKET_VIEW,
                idx,
                len(chunks),
                len(chunk),
                normalized_condition_id,
                exc,
            )
            raise

        chunk_rows = res.data if res and res.data else []
        results.extend(chunk_rows)

    logger.warning(
        "[DB_CARD_PRICE_QUERY] checkpoint=after-execute table=%s total_rows=%s chunk_count=%s",
        _LATEST_CARD_MARKET_VIEW,
        len(results),
        len(chunks),
    )
    return results


def insert_card_variant_prices_batch(price_rows: List[Dict[str, Any]]) -> List[int]:
    """
    Insert multiple price rows in a single batch operation.
    
    Args:
        price_rows: List of price dictionaries to insert
        
    Returns:
        List of IDs of the newly inserted price records
        
    Raises:
        RuntimeError: If insertion fails
    """
    stats = insert_card_variant_prices_batch_with_stats(price_rows)
    return stats["inserted_ids"]


def insert_card_variant_prices_batch_with_stats(price_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Batch insert card prices with same-day duplicate suppression across all price fields.

    Classification per row:
    - INSERT : no same-day row exists for this entity+condition+source
    - UPDATE : same-day row exists but market_price, high_price, or low_price changed
    - SKIP   : same-day row exists and all relevant price fields are identical
    """
    if not price_rows:
        return {
            "attempted_rows": 0,
            "inserted_count": 0,
            "inserted_ids": [],
            "updated_count": 0,
            "skipped_duplicates": 0,
            "skipped_existing_duplicates": 0,
            "duplicate_rows_in_batch": 0,
            "db_batch_operations": 0,
        }

    normalized_rows = [_normalize_price_row(row) for row in price_rows]
    existing_by_identity, dedupe_query_ops = _fetch_existing_same_day_observations(normalized_rows)

    rows_to_insert: List[Dict[str, Any]] = []
    rows_to_update: List[Tuple[int, Dict[str, Any], Dict[str, Any]]] = []  # (existing_id, price_fields_dict, normalized_row)
    seen_identity_keys: Set[str] = set()
    skipped_existing_duplicates = 0
    duplicate_rows_in_batch = 0

    for row in normalized_rows:
        identity = _identity_key(row)

        # Within-batch dedup: same entity+source+day seen more than once in this batch
        if identity in seen_identity_keys:
            duplicate_rows_in_batch += 1
            continue
        seen_identity_keys.add(identity)

        if identity in existing_by_identity:
            existing = existing_by_identity[identity]
            if _prices_match(row, existing):
                # All price fields identical — true duplicate, skip
                skipped_existing_duplicates += 1
            else:
                # Same-day row exists but a price field changed — update it
                rows_to_update.append((
                    existing["id"],
                    {
                        "market_price": row.get("market_price"),
                        "high_price": row.get("high_price"),
                        "low_price": row.get("low_price"),
                    },
                    row,
                ))
        else:
            rows_to_insert.append(row)

    db_ops = dedupe_query_ops
    inserted_ids: List[int] = []
    updated_count = 0
    updated_rows: List[Dict[str, Any]] = []

    # Batch INSERT new rows
    if rows_to_insert:
        last_insert_error = None
        for attempt in range(3):
            try:
                fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
                res = (
                    fresh_client.table("card_variant_price_observations")
                    .insert(rows_to_insert)
                    .execute()
                )
                if res is None:
                    raise RuntimeError("Batch insert prices returned no response object")
                inserted = res.data
                if inserted is None:
                    raise RuntimeError("Batch insert returned no data")
                inserted_ids = [item["id"] for item in inserted]
                db_ops += 1
                break
            except APIError as e:
                last_insert_error = str(e)
                if "schema cache" in last_insert_error.lower():
                    logger.warning("Schema cache error on batch insert attempt %d/3, retrying...", attempt + 1)
                    if attempt < 2:
                        time.sleep(1)
                        continue
                raise RuntimeError(f"Failed to batch insert card variant prices: {last_insert_error}")
            except RuntimeError as e:
                last_insert_error = str(e)
                if "schema cache" in last_insert_error.lower() and attempt < 2:
                    time.sleep(1)
                    continue
                raise
        else:
            raise RuntimeError(f"Failed to batch insert card prices after 3 retries: {last_insert_error}")

    # UPDATE changed same-day rows individually (price drift within a day is rare)
    if rows_to_update:
        update_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        for existing_id, price_fields, normalized_row in rows_to_update:
            db_ops += 1
            try:
                update_client.table("card_variant_price_observations").update(price_fields).eq("id", existing_id).execute()
                updated_count += 1
                updated_rows.append(normalized_row)
            except Exception as exc:
                logger.warning("Failed to update card price observation id=%s: %s", existing_id, exc)

    _refresh_pokemon_set_value_history_for_price_rows([*rows_to_insert, *updated_rows])

    return {
        "attempted_rows": len(price_rows),
        "inserted_count": len(inserted_ids),
        "inserted_ids": inserted_ids,
        "updated_count": updated_count,
        "skipped_duplicates": skipped_existing_duplicates + duplicate_rows_in_batch,
        "skipped_existing_duplicates": skipped_existing_duplicates,
        "duplicate_rows_in_batch": duplicate_rows_in_batch,
        "db_batch_operations": db_ops,
    }
