import base64
import json
import logging
import os
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple, Set

from supabase import create_client
from postgrest.exceptions import APIError

from ..clients.supabase_client import SUPABASE_URL, SUPABASE_KEY
from backend.db.services.supabase_persistence_retry import run_supabase_with_transient_retry


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
PRICE_WRITE_CHUNK_SIZE = 100
_CANONICAL_REFRESH_SINGULAR = "refresh_pokemon_canonical_card_market_prices_latest_for_variant"
_CANONICAL_REFRESH_PLURAL = "refresh_pokemon_canonical_card_market_prices_latest_for_variants"
_canonical_refresh_rpc_name: Optional[str] = None


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

def _captured_date(value: Any) -> str:
    """Return the canonical DATE value used by observation tables."""
    if isinstance(value, str) and len(value) >= 10:
        return datetime.fromisoformat(value[:10]).date().isoformat()
    return _parse_captured_at(value).date().isoformat()


def _normalize_price_row(price_row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a price row before insert."""
    normalized = dict(price_row)
    normalized["captured_at"] = _captured_date(normalized.get("captured_at"))
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
    return "|".join(
        [
            str(price_row.get("card_variant_id")),
            str(price_row.get("condition_id")),
            str(price_row.get("source") or "UNKNOWN"),
            _captured_date(price_row.get("captured_at")),
        ]
    )


def _prices_match(incoming: Dict[str, Any], existing: Dict[str, Any]) -> bool:
    """Return True only if all relevant price fields (market_price, high_price, low_price) are identical."""
    for field in ("market_price", "high_price", "low_price"):
        if _normalize_market_price(incoming.get(field)) != _normalize_market_price(existing.get(field)):
            return False
    return True


def _is_missing_rpc(exc: Exception) -> bool:
    detail = f"{getattr(exc, 'code', '')} {exc}".lower()
    return "pgrst202" in detail or ("404" in detail and "function" in detail)


def _refresh_canonical_prices(variant_ids: List[str]) -> None:
    """Call the deployed singular contract without a known-404 hot path.

    The repository historically declares the plural RPC while the deployed
    production schema exposes the singular RPC. Resolution is cached once per
    process. Operators may pin either compatible contract through the env var.
    """
    global _canonical_refresh_rpc_name
    configured = os.getenv("POKEMON_CANONICAL_REFRESH_RPC_NAME", "").strip()
    candidates = ([configured] if configured else
                  [_CANONICAL_REFRESH_SINGULAR, _CANONICAL_REFRESH_PLURAL])
    if _canonical_refresh_rpc_name:
        candidates = [_canonical_refresh_rpc_name]

    last_error: Optional[Exception] = None
    for index, rpc_name in enumerate(candidates):
        try:
            run_supabase_with_transient_retry(
                lambda client, _attempt, rpc_name=rpc_name: client.rpc(
                    rpc_name, {"p_card_variant_ids": variant_ids}).execute(),
                operation_name="refresh_pokemon_canonical_card_market_prices_latest",
            )
            _canonical_refresh_rpc_name = rpc_name
            return
        except Exception as exc:
            last_error = exc
            if configured or _canonical_refresh_rpc_name or not _is_missing_rpc(exc):
                raise
            if index + 1 < len(candidates):
                continue
            raise
    if last_error:
        raise last_error


def _refresh_pokemon_set_value_history_for_price_rows(price_rows: List[Dict[str, Any]]) -> None:
    changed_rows = [row for row in price_rows if row.get("card_variant_id")]
    if not changed_rows:
        return

    variant_ids = sorted({str(row.get("card_variant_id")) for row in changed_rows if row.get("card_variant_id")})
    captured_dates = [
        _captured_date(row.get("captured_at"))
        for row in changed_rows
        if row.get("captured_at")
    ]
    start_date = min(captured_dates) if captured_dates else datetime.now(timezone.utc).date().isoformat()

    try:
        run_supabase_with_transient_retry(
            lambda client, _attempt: client.rpc(
                "refresh_pokemon_set_value_daily_history_for_variants",
                {"p_card_variant_ids": variant_ids, "p_start_date": start_date},
            ).execute(),
            operation_name="refresh_pokemon_set_value_daily_history_for_variants",
        )
    except Exception as exc:
        logger.warning(
            "Unable to refresh pokemon_set_value_daily_history for %s changed card variant price row(s): %s",
            len(changed_rows),
            exc,
        )

    try:
        _refresh_canonical_prices(variant_ids)
    except Exception as exc:
        logger.warning(
            "Unable to refresh canonical Pokemon selected prices for %s changed card variant price row(s): %s",
            len(changed_rows),
            exc,
        )


def _fetch_existing_same_day_observations(
    normalized_rows: List[Dict[str, Any]],
    client=None,
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
        day_key = _captured_date(row.get("captured_at"))
        rows_by_day.setdefault(day_key, []).append(row)

    existing_by_identity: Dict[str, Dict[str, Any]] = {}
    query_count = 0

    for day_key, day_rows in rows_by_day.items():
        variant_ids = sorted({row.get("card_variant_id") for row in day_rows if row.get("card_variant_id") is not None})
        condition_ids = sorted({row.get("condition_id") for row in day_rows if row.get("condition_id") is not None})
        sources = sorted({(row.get("source") or "UNKNOWN") for row in day_rows})

        if not variant_ids or not condition_ids:
            continue

        fresh_client = client or create_client(SUPABASE_URL, SUPABASE_KEY)
        query_count += 1
        res = (
            fresh_client.table("card_variant_price_observations")
            .select("id, card_variant_id, condition_id, source, captured_at, market_price, high_price, low_price")
            .in_("card_variant_id", variant_ids)
            .in_("condition_id", condition_ids)
            .in_("source", sources)
            .eq("captured_at", day_key)
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
    stats = insert_card_variant_prices_batch_with_stats([price_row])
    if not stats["inserted_ids"]:
        raise RuntimeError("Card variant price was reconciled without an observation id")
    return stats["inserted_ids"][0]



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
            "price_read_operations": 0,
            "price_write_operations": 0,
        }

    normalized_rows = [_normalize_price_row(row) for row in price_rows]
    unique_rows: List[Dict[str, Any]] = []
    seen_identity_keys: Set[str] = set()
    duplicate_rows_in_batch = 0
    for row in normalized_rows:
        identity = _identity_key(row)
        if identity in seen_identity_keys:
            duplicate_rows_in_batch += 1
            continue
        seen_identity_keys.add(identity)
        unique_rows.append(row)

    inserted_ids: List[int] = []
    updated_count = 0
    skipped_existing_duplicates = 0
    db_ops = 0
    price_read_ops = 0
    price_write_ops = 0
    changed_rows: List[Dict[str, Any]] = []

    for offset in range(0, len(unique_rows), PRICE_WRITE_CHUNK_SIZE):
        chunk = unique_rows[offset:offset + PRICE_WRITE_CHUNK_SIZE]
        initial_existing: Set[str] = set()
        attempted_updates: Set[str] = set()
        attempted_inserts: Set[str] = set()

        def persist_chunk(client, attempt):
            existing, query_ops = _fetch_existing_same_day_observations(chunk, client=client)
            if attempt == 1:
                initial_existing.update(existing)
            ids = []
            updates = 0
            local_changed = []
            local_ops = query_ops
            missing = []
            for row in chunk:
                identity = _identity_key(row)
                current = existing.get(identity)
                if current is None:
                    missing.append(row)
                elif _prices_match(row, current):
                    if identity in attempted_updates:
                        updates += 1
                        local_changed.append(row)
                    elif identity in attempted_inserts:
                        ids.append(current["id"])
                        local_changed.append(row)
                else:
                    fields = {key: row.get(key) for key in ("market_price", "high_price", "low_price")}
                    client.table("card_variant_price_observations").update(fields).eq("id", current["id"]).execute()
                    updates += 1
                    local_ops += 1
                    local_changed.append(row)
                    attempted_updates.add(identity)
            if missing:
                attempted_inserts.update(_identity_key(row) for row in missing)
                response = client.table("card_variant_price_observations").insert(missing).execute()
                if response is None or response.data is None:
                    raise RuntimeError("Batch insert prices returned no data")
                ids.extend(item["id"] for item in response.data)
                local_changed.extend(missing)
                local_ops += 1
            return ids, updates, local_changed, local_ops, query_ops, local_ops - query_ops

        chunk_ids, chunk_updates, chunk_changed, chunk_ops, chunk_reads, chunk_writes = run_supabase_with_transient_retry(
            persist_chunk,
            operation_name=f"card_variant_prices_chunk_{offset // PRICE_WRITE_CHUNK_SIZE}",
        )
        inserted_ids.extend(chunk_ids)
        updated_count += chunk_updates
        changed_rows.extend(chunk_changed)
        db_ops += chunk_ops
        price_read_ops += chunk_reads
        price_write_ops += chunk_writes
        skipped_existing_duplicates += len(initial_existing) - chunk_updates

    _refresh_pokemon_set_value_history_for_price_rows(changed_rows)

    return {
        "attempted_rows": len(price_rows),
        "inserted_count": len(inserted_ids),
        "inserted_ids": inserted_ids,
        "updated_count": updated_count,
        "skipped_duplicates": skipped_existing_duplicates + duplicate_rows_in_batch,
        "skipped_existing_duplicates": skipped_existing_duplicates,
        "duplicate_rows_in_batch": duplicate_rows_in_batch,
        "db_batch_operations": db_ops,
        "price_read_operations": price_read_ops,
        "price_write_operations": price_write_ops,
    }
