from ..clients.supabase_client import supabase, SUPABASE_URL, SUPABASE_KEY
from supabase import create_client
from postgrest.exceptions import APIError
from typing import Dict, Any, Optional, List, Tuple, Set
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import time


def _parse_captured_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = datetime.now(timezone.utc)

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_market_price(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def _normalize_price_row(price_row: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(price_row)
    normalized["captured_at"] = _parse_captured_at(normalized.get("captured_at")).isoformat()
    normalized["source"] = normalized.get("source") or "UNKNOWN"
    normalized["currency"] = normalized.get("currency") or "USD"
    return normalized


def _identity_key(price_row: Dict[str, Any]) -> str:
    """Build entity+source+day key (no price fields) to identify same-day rows."""
    captured_at_dt = _parse_captured_at(price_row.get("captured_at"))
    return "|".join(
        [
            str(price_row.get("sealed_product_id")),
            str(price_row.get("source") or "UNKNOWN"),
            captured_at_dt.date().isoformat(),
        ]
    )


def _prices_match(incoming: Dict[str, Any], existing: Dict[str, Any]) -> bool:
    """Return True only if all relevant price fields (market_price, low_price) are identical."""
    for field in ("market_price", "low_price"):
        if _normalize_market_price(incoming.get(field)) != _normalize_market_price(existing.get(field)):
            return False
    return True


def _fetch_existing_same_day_observations(
    normalized_rows: List[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """
    Fetch existing same-day rows keyed by identity_key.
    Returns (Dict[identity_key -> existing_row], query_count).
    Each existing_row contains: id, market_price, low_price.
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
        sealed_product_ids = sorted({row.get("sealed_product_id") for row in day_rows if row.get("sealed_product_id") is not None})
        sources = sorted({(row.get("source") or "UNKNOWN") for row in day_rows})

        if not sealed_product_ids:
            continue

        fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        query_count += 1
        res = (
            fresh_client.table("sealed_product_price_observations")
            .select("id, sealed_product_id, source, captured_at, market_price, low_price")
            .in_("sealed_product_id", sealed_product_ids)
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


def insert_sealed_product_price(price_row: Dict[str, Any]) -> int:
    """
    Insert a price row into `sealed_product_price_observations`.
    
    Args:
        price_row: Should include sealed_product_id, market_price, source, captured_at.
                   Optional: currency (defaults to USD in DB)
        
    Returns:
        The id of the newly inserted price record
        
    Raises:
        RuntimeError: If insertion fails
    """
    print(f"[DEBUG] Inserting sealed price with data: {price_row}")
    
    # Retry mechanism for schema cache issues
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = fresh_client.table("sealed_product_price_observations").insert(price_row).execute()
            if res is None:
                raise RuntimeError("Insert sealed product price returned no response object")
            
            inserted = res.data
            if not inserted:
                raise RuntimeError("Insert returned no data")
            
            return inserted[0]["id"]
        
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            
            # Check if it's a schema cache error
            if "schema cache" in error_msg.lower():
                print(f"[WARN]  Schema cache error on attempt {attempt + 1}/{max_retries}, retrying...")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            else:
                # Not a schema cache error, fail immediately
                print(f"[DEBUG] API Error: {error_msg}")
                raise RuntimeError(f"Failed to insert sealed product price: {error_msg}")
        
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                print(f"[WARN]  Retrying after error: {e}")
                time.sleep(1)
                continue
            raise
    
    raise RuntimeError(f"Failed to insert sealed product price after {max_retries} retries: {last_error}")


def get_latest_price(sealed_product_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the latest market price row for a sealed product.
    
    Args:
        sealed_product_id: The ID of the sealed product
        
    Returns:
        The latest market view row, or None if not found
    """
    fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    res = (
        fresh_client.table("sealed_product_market_usd_latest")
        .select("*")
        .eq("sealed_product_id", sealed_product_id)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None


def insert_sealed_product_prices_batch(price_rows: List[Dict[str, Any]]) -> List[int]:
    """
    Insert multiple sealed product price rows in a single batch operation.
    
    Args:
        price_rows: List of price dictionaries to insert
        
    Returns:
        List of IDs of the newly inserted price records
        
    Raises:
        RuntimeError: If insertion fails
    """
    stats = insert_sealed_product_prices_batch_with_stats(price_rows)
    return stats["inserted_ids"]


def insert_sealed_product_prices_batch_with_stats(price_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Batch insert sealed prices with same-day duplicate suppression across all price fields.

    Classification per row:
    - INSERT : no same-day row exists for this entity+source
    - UPDATE : same-day row exists but market_price or low_price changed
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
    rows_to_update: List[Tuple[int, Dict[str, Any]]] = []  # (existing_id, price_fields_dict)
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
                        "low_price": row.get("low_price"),
                    },
                ))
        else:
            rows_to_insert.append(row)

    db_ops = dedupe_query_ops
    inserted_ids: List[int] = []
    updated_count = 0

    # Batch INSERT new rows
    if rows_to_insert:
        last_insert_error = None
        for attempt in range(3):
            try:
                fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
                res = fresh_client.table("sealed_product_price_observations").insert(rows_to_insert).execute()

                if res is None:
                    raise RuntimeError("Batch insert sealed product prices returned no response object")

                inserted = res.data
                if inserted is None:
                    raise RuntimeError("Batch insert returned no data")

                inserted_ids = [item["id"] for item in inserted]
                db_ops += 1
                break
            except APIError as e:
                last_insert_error = str(e)
                if "schema cache" in last_insert_error.lower():
                    print(f"[WARN]  Schema cache error on batch insert attempt {attempt + 1}/3, retrying...")
                    if attempt < 2:
                        time.sleep(1)
                        continue
                raise RuntimeError(f"Failed to batch insert sealed product prices: {last_insert_error}")
            except RuntimeError as e:
                last_insert_error = str(e)
                if "schema cache" in last_insert_error.lower() and attempt < 2:
                    time.sleep(1)
                    continue
                raise
        else:
            raise RuntimeError(f"Failed to batch insert sealed product prices after 3 retries: {last_insert_error}")

    # UPDATE changed same-day rows individually (price drift within a day is rare)
    if rows_to_update:
        update_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        for existing_id, price_fields in rows_to_update:
            db_ops += 1
            try:
                update_client.table("sealed_product_price_observations").update(price_fields).eq("id", existing_id).execute()
                updated_count += 1
            except Exception as exc:
                print(f"[WARN]  Failed to update sealed price observation id={existing_id}: {exc}")

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

