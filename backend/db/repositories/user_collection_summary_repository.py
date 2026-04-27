import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..clients.supabase_client import supabase
from .card_variant_prices_repository import get_latest_price as get_latest_card_variant_price
from .graded_card_variant_prices_repository import get_latest_price as get_latest_graded_card_variant_price
from .sealed_product_prices_repository import get_latest_price as get_latest_sealed_product_price


logger = logging.getLogger(__name__)

SUMMARY_SELECT_COLUMNS = (
    "user_id,portfolio_value,cards_count,sealed_count,graded_count,"
    "portfolio_delta_1d,portfolio_delta_7d,portfolio_delta_3m,portfolio_delta_6m,portfolio_delta_1y,portfolio_delta_lifetime,"
    "portfolio_delta_pct_1d,portfolio_delta_pct_7d,portfolio_delta_pct_3m,portfolio_delta_pct_6m,portfolio_delta_pct_1y,portfolio_delta_pct_lifetime,"
    "computed_at,is_stale"
)

_NIGHTLY_PRICING_SAMPLE_LIMIT = 25


def _timer_elapsed_ms(start: float) -> float:
    """Return elapsed time in milliseconds with lightweight rounding."""
    return round((perf_counter() - start) * 1000, 3)


def _resolve_snapshot_date(snapshot_date: Optional[str]) -> str:
    """Normalize a nightly snapshot date to YYYY-MM-DD in UTC."""
    if snapshot_date:
        normalized = snapshot_date.strip()
        if not normalized:
            raise ValueError("snapshot_date cannot be blank")
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            try:
                return datetime.strptime(normalized, "%Y-%m-%d").date().isoformat()
            except ValueError as exc:
                raise ValueError(f"Invalid snapshot_date: {snapshot_date}") from exc

    return datetime.now(timezone.utc).date().isoformat()


def get_nightly_snapshot_pricing_freshness(snapshot_date: Optional[str] = None) -> Dict[str, Any]:
    """Verify held assets have snapshot-date pricing using the bounded SQL freshness RPC."""
    total_started = perf_counter()
    resolved_snapshot_date = _resolve_snapshot_date(snapshot_date)
    fallback_timings = {
        "held_asset_load_ms": 0.0,
        "card_freshness_check_ms": 0.0,
        "sealed_freshness_check_ms": 0.0,
        "graded_freshness_check_ms": 0.0,
        "total_ms": 0.0,
    }
    fallback_query_path = {
        "held_asset_source": [
            "user_card_holdings(quantity>0)",
            "user_sealed_product_holdings(quantity>0)",
            "user_graded_card_holdings(quantity>0)",
        ],
        "card_check_source": "card_variant_price_observations(captured_at)",
        "sealed_check_source": "sealed_product_price_observations(captured_at)",
        "graded_check_source": "graded_card_market_latest(captured_at)",
        "uses_distinct_held_assets": True,
        "loads_full_holdings_rows": False,
        "loads_full_latest_views": False,
        "notes": [
            "Card and sealed freshness use snapshot-date observation tables with minimal columns.",
            "Graded freshness falls back to graded_card_market_latest because no graded observation table was found in repo migrations.",
            "Missing asset samples are fetched only after freshness is decided and are bounded by sample limit.",
        ],
    }

    try:
        payload = {
            "p_snapshot_date": resolved_snapshot_date,
            "p_sample_limit": _NIGHTLY_PRICING_SAMPLE_LIMIT,
        }
        response = supabase.rpc("get_nightly_snapshot_pricing_freshness", payload).execute()
        data = response.data if response else None
        result = data[0] if isinstance(data, list) and data else data

        if not isinstance(result, dict):
            raise RuntimeError("Nightly pricing freshness RPC returned an unexpected payload")

        result.setdefault("snapshot_date", resolved_snapshot_date)
        result.setdefault("status", "incomplete")
        result.setdefault("check_completed", False)
        result.setdefault("is_fresh", False)
        result.setdefault("held_asset_counts", {"cards": 0, "sealed": 0, "graded": 0})
        result.setdefault("fresh_asset_counts", {"cards": 0, "sealed": 0, "graded": 0})
        result.setdefault("missing_asset_counts", {"cards": 0, "sealed": 0, "graded": 0, "total": 0})
        result.setdefault("missing_assets_sample", [])
        result.setdefault("query_path", fallback_query_path)
        timings = result.get("timings_ms") if isinstance(result.get("timings_ms"), dict) else {}
        timings.setdefault("total_ms", _timer_elapsed_ms(total_started))
        result["timings_ms"] = timings
        if result.get("warning") is None and not result.get("is_fresh"):
            result["warning"] = (
                f"Pricing freshness incomplete for snapshot_date={resolved_snapshot_date}; "
                "nightly snapshot skipped."
            )
        logger.info(
            "pricing_freshness.snapshot_date=%s status=%s held_asset_counts=%s missing_asset_counts=%s timings_ms=%s",
            result.get("snapshot_date"),
            result["status"],
            result.get("held_asset_counts"),
            result["missing_asset_counts"],
            result["timings_ms"],
        )
        return result
    except Exception as exc:
        fallback_timings["total_ms"] = _timer_elapsed_ms(total_started)
        logger.exception(
            "pricing_freshness.failed snapshot_date=%s error_type=%s error=%s timings_ms=%s",
            resolved_snapshot_date,
            type(exc).__name__,
            exc,
            fallback_timings,
        )
        return {
            "snapshot_date": resolved_snapshot_date,
            "status": "incomplete",
            "check_completed": False,
            "is_fresh": False,
            "held_asset_counts": {"cards": 0, "sealed": 0, "graded": 0},
            "fresh_asset_counts": {"cards": 0, "sealed": 0, "graded": 0},
            "missing_asset_counts": {"cards": 0, "sealed": 0, "graded": 0, "total": 0},
            "missing_assets_sample": [],
            "warning": (
                f"Pricing freshness check could not complete for snapshot_date={resolved_snapshot_date}; "
                "nightly snapshot skipped."
            ),
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
            "timings_ms": fallback_timings,
            "query_path": fallback_query_path,
        }


def _extract_price(value: Any) -> float:
    """Extract a numeric price from relation payloads or scalar values."""
    if isinstance(value, list):
        if not value:
            return 0.0
        candidate = value[0]
        if isinstance(candidate, dict):
            raw = candidate.get("price")
            if raw is None:
                return 0.0
            try:
                parsed = float(raw)
                return parsed if parsed >= 0 else 0.0
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    if isinstance(value, dict):
        raw = value.get("price")
        if raw is None:
            return 0.0
        try:
            parsed = float(raw)
            return parsed if parsed >= 0 else 0.0
        except (TypeError, ValueError):
            return 0.0

    try:
        parsed = float(value)
        return parsed if parsed >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def _to_quantity(value: Any) -> int:
    """Normalize quantity values to non-negative integers."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else 0
    return 0


def _extract_market_price(row: Dict[str, Any], relation_key: str) -> float:
    """Extract market price from a joined relation or direct row fields."""
    relation_price = _extract_price(row.get(relation_key))
    if relation_price:
        return relation_price

    for field_name in ("market_price", "current_market_price", "price"):
        field_value = row.get(field_name)
        if field_value is None:
            continue
        try:
            parsed = float(field_value)
            if parsed >= 0:
                return parsed
        except (TypeError, ValueError):
            continue

    return 0.0


def _latest_card_market_price(card_variant_id: Any, condition_id: Any) -> float:
    """Resolve latest card market price from canonical repository helper."""
    if card_variant_id is None or condition_id is None:
        logger.warning(
            "[portfolio-debug] raw card price skipped card_variant_id=%s condition_id=%s reason=missing_lookup_key",
            card_variant_id,
            condition_id,
        )
        return 0.0

    try:
        price_row = get_latest_card_variant_price(card_variant_id, condition_id)
    except Exception as exc:
        logger.warning(
            "[portfolio-debug] raw card price lookup error card_variant_id=%s condition_id=%s error_type=%s error=%s",
            card_variant_id,
            condition_id,
            type(exc).__name__,
            exc,
        )
        return 0.0

    if not price_row:
        logger.warning(
            "[portfolio-debug] raw card price lookup empty card_variant_id=%s condition_id=%s",
            card_variant_id,
            condition_id,
        )
        return 0.0
    market_price = _extract_market_price(price_row, "")
    logger.warning(
        "[portfolio-debug] raw card price resolved card_variant_id=%s condition_id=%s market_price=%s",
        card_variant_id,
        condition_id,
        market_price,
    )
    return market_price


def _latest_sealed_market_price(sealed_product_id: Any) -> float:
    """Resolve latest sealed market price from canonical repository helper."""
    if sealed_product_id is None:
        logger.warning("[portfolio-debug] sealed price skipped sealed_product_id=None")
        return 0.0

    try:
        price_row = get_latest_sealed_product_price(sealed_product_id)
    except Exception as exc:
        logger.warning(
            "[portfolio-debug] sealed price lookup error sealed_product_id=%s error_type=%s error=%s",
            sealed_product_id,
            type(exc).__name__,
            exc,
        )
        return 0.0

    logger.warning(
        "[portfolio-debug] sealed price raw row sealed_product_id=%s row_found=%s raw_row=%s",
        sealed_product_id,
        bool(price_row),
        price_row,
    )
    if not price_row:
        return 0.0
    market_price = _extract_market_price(price_row, "")
    logger.warning(
        "[portfolio-debug] sealed price resolved sealed_product_id=%s market_price=%s",
        sealed_product_id,
        market_price,
    )
    return market_price


def _latest_graded_market_price(graded_card_variant_id: Any) -> float:
    """Resolve latest graded market price from canonical repository helper."""
    if graded_card_variant_id is None:
        logger.warning("[portfolio-debug] graded price skipped graded_card_variant_id=None")
        return 0.0

    try:
        price_row = get_latest_graded_card_variant_price(graded_card_variant_id)
    except Exception as exc:
        logger.warning(
            "[portfolio-debug] graded price lookup error graded_card_variant_id=%s error_type=%s error=%s",
            graded_card_variant_id,
            type(exc).__name__,
            exc,
        )
        return 0.0

    logger.warning(
        "[portfolio-debug] graded price raw row graded_card_variant_id=%s row_found=%s raw_row=%s",
        graded_card_variant_id,
        bool(price_row),
        price_row,
    )
    if not price_row:
        return 0.0
    market_price = _extract_market_price(price_row, "")
    logger.warning(
        "[portfolio-debug] graded price resolved graded_card_variant_id=%s market_price=%s",
        graded_card_variant_id,
        market_price,
    )
    return market_price


def _safe_fetch_rows(table_name: str, select_candidates: List[str], user_id: UUID) -> List[Dict[str, Any]]:
    """Execute table query with select fallbacks and return rows or empty list."""
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")

    failures: List[str] = []
    for select_clause in select_candidates:
        try:
            response = (
                supabase.table(table_name)
                .select(select_clause)
                .eq("user_id", str(user_id))
                .execute()
            )
            rows = response.data if response and response.data else []
            logger.warning(
                "[portfolio-debug] holdings fetch table=%s user_id=%s select=%s row_count=%s",
                table_name,
                user_id,
                select_clause,
                len(rows),
            )
            return rows
        except Exception as exc:
            failures.append(f"{select_clause} -> {type(exc).__name__}: {exc}")
            continue

    if failures:
        logger.error(
            "Failed fetching summary rows for table '%s' and user '%s': %s",
            table_name,
            user_id,
            " | ".join(failures),
        )
        raise RuntimeError(
            f"Failed to fetch rows for table '{table_name}' using provided select candidates"
        )

    return []


def load_user_collection_summary_snapshot(user_id: UUID) -> Optional[Dict[str, Any]]:
    """Load the precomputed summary row for a user from public.user_collection_summary."""
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")

    response = (
        supabase.table("user_collection_summary")
        .select(SUMMARY_SELECT_COLUMNS)
        .eq("user_id", str(user_id))
        .limit(1)
        .execute()
    )

    rows = response.data if response and response.data else []
    if not rows:
        return None

    row = rows[0]
    return row if isinstance(row, dict) else None


def upsert_user_collection_summary(user_id: UUID, summary_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a user's summary row and return the upserted row."""
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")

    payload = {
        "user_id": str(user_id),
        "portfolio_value": summary_payload.get("portfolio_value", 0.0),
        "cards_count": summary_payload.get("cards_count", 0),
        "sealed_count": summary_payload.get("sealed_count", 0),
        "graded_count": summary_payload.get("graded_count", 0),
    }

    response = (
        supabase.table("user_collection_summary")
        .upsert(payload, on_conflict="user_id")
        .execute()
    )

    rows = response.data if response and response.data else []
    if rows and isinstance(rows[0], dict):
        return rows[0]

    # Fallback read keeps the write path stable even if upsert response payload changes.
    refreshed = load_user_collection_summary_snapshot(user_id)
    if isinstance(refreshed, dict):
        return refreshed
    raise RuntimeError(f"Summary upsert completed but no row was returned for user_id={user_id}")


def snapshot_user_portfolio_history(user_id: UUID) -> None:
    """Execute DB function that writes/updates one daily history snapshot for a user."""
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")
    supabase.rpc("snapshot_user_portfolio_history", {"p_user_id": str(user_id)}).execute()


def refresh_user_collection_deltas(user_id: Optional[UUID] = None) -> None:
    """Execute DB function to refresh portfolio delta fields in user_collection_summary."""
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")

    payload: Dict[str, Any] = {"p_user_id": str(user_id)} if user_id else {}
    supabase.rpc("refresh_user_collection_deltas", payload).execute()


def snapshot_all_user_portfolio_history() -> None:
    """Execute DB function that snapshots daily history for all users."""
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")
    supabase.rpc("snapshot_all_user_portfolio_history").execute()


def has_stale_user_collection_summary_rows() -> bool:
    """Return True when at least one summary row is marked stale."""
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")

    response = (
        supabase.table("user_collection_summary")
        .select("user_id")
        .eq("is_stale", True)
        .limit(1)
        .execute()
    )
    rows = response.data if response and response.data else []
    return bool(rows)


def load_user_collection_for_summary(user_id: UUID) -> Dict[str, List[Dict[str, Any]]]:
    """Load normalized holdings payloads for summary calculations."""
    card_rows = _safe_fetch_rows(
        "user_card_holdings",
        [
            "id,card_variant_id,condition_id,quantity",
        ],
        user_id,
    )

    card_payload: List[Dict[str, Any]] = []
    for row in card_rows:
        card_variant_id = row.get("card_variant_id")
        condition_id = row.get("condition_id")
        quantity = _to_quantity(row.get("quantity"))
        market_price = _latest_card_market_price(card_variant_id, condition_id)
        logger.warning(
            "[portfolio-debug] raw card holding holding_id=%s card_variant_id=%s condition_id=%s quantity=%s market_price=%s",
            row.get("id"),
            card_variant_id,
            condition_id,
            quantity,
            market_price,
        )
        card_payload.append(
            {
                "holding_id": row.get("id"),
                "card_variant_id": card_variant_id,
                "condition_id": condition_id,
                "quantity": quantity,
                "market_price": market_price,
            }
        )

    sealed_rows = _safe_fetch_rows(
        "user_sealed_product_holdings",
        [
            "id,sealed_product_id,quantity",
        ],
        user_id,
    )

    sealed_payload: List[Dict[str, Any]] = []
    for row in sealed_rows:
        sealed_product_id = row.get("sealed_product_id")
        quantity = _to_quantity(row.get("quantity"))
        market_price = _latest_sealed_market_price(sealed_product_id)
        logger.warning(
            "[portfolio-debug] sealed holding holding_id=%s sealed_product_id=%s quantity=%s market_price=%s",
            row.get("id"),
            sealed_product_id,
            quantity,
            market_price,
        )
        sealed_payload.append(
            {
                "holding_id": row.get("id"),
                "sealed_product_id": sealed_product_id,
                "quantity": quantity,
                "market_price": market_price,
            }
        )

    graded_rows = _safe_fetch_rows(
        "user_graded_card_holdings",
        [
            "id,graded_card_variant_id,certification_number,quantity",
        ],
        user_id,
    )

    graded_payload: List[Dict[str, Any]] = []
    for row in graded_rows:
        graded_card_variant_id = row.get("graded_card_variant_id")
        quantity = _to_quantity(row.get("quantity"))
        market_price = _latest_graded_market_price(graded_card_variant_id)
        logger.warning(
            "[portfolio-debug] graded holding holding_id=%s graded_card_variant_id=%s quantity=%s market_price=%s",
            row.get("id"),
            graded_card_variant_id,
            quantity,
            market_price,
        )
        graded_payload.append(
            {
                "holding_id": row.get("id"),
                "graded_card_variant_id": graded_card_variant_id,
                "certification_number": row.get("certification_number"),
                "quantity": quantity,
                "market_price": market_price,
            }
        )

    return {
        "user_card_holdings": card_payload,
        "user_sealed_product_holdings": sealed_payload,
        "user_graded_card_holdings": graded_payload,
    }


def run_nightly_portfolio_refresh(current_date: Optional[str] = None) -> None:
    """Execute DB function for nightly portfolio refresh across all users.
    
    This orchestrates a full portfolio refresh and history snapshot cycle.
    Intended to be called once nightly around 3:00 AM.
    
    Args:
        current_date: Optional ISO date string (YYYY-MM-DD). If not provided, uses today's date.
        
    Raises:
        RuntimeError: If DB function call fails
    """
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")
    
    payload: Dict[str, Any] = {}
    if current_date:
        payload["p_current_date"] = current_date
    
    try:
        supabase.rpc("run_nightly_portfolio_refresh", payload).execute()
        logger.info("repository: run_nightly_portfolio_refresh executed successfully")
    except Exception as exc:
        logger.exception(
            "repository: run_nightly_portfolio_refresh failed error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        raise RuntimeError("Failed to execute nightly portfolio refresh") from exc


def refresh_user_collection_summary_live(user_id: UUID) -> None:
    """Immediately refresh a user's summary (live/active refresh path).
    
    This is called after holdings changes to ensure summary is fresh immediately,
    without waiting for nightly batch job.
    
    Args:
        user_id: UUID of the user whose summary to refresh
        
    Raises:
        RuntimeError: If DB function call fails
    """
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")
    
    try:
        supabase.rpc("refresh_user_collection_summary_live", {"p_user_id": str(user_id)}).execute()
        logger.info("repository: refresh_user_collection_summary_live user_id=%s executed successfully", user_id)
    except Exception as exc:
        logger.exception(
            "repository: refresh_user_collection_summary_live user_id=%s failed error_type=%s error=%s",
            user_id,
            type(exc).__name__,
            exc,
        )
        raise RuntimeError(f"Failed to refresh summary live for user {user_id}") from exc


def ensure_fresh_user_collection_summary(user_id: UUID) -> None:
    """Ensure user collection summary is fresh before returning it.
    
    This is a safety net called before dashboard/summary reads to guarantee freshness.
    If summary is marked stale, it triggers a refresh immediately.
    
    Args:
        user_id: UUID of the user
        
    Raises:
        RuntimeError: If DB function call fails
    """
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")
    
    try:
        supabase.rpc("ensure_fresh_user_collection_summary", {"p_user_id": str(user_id)}).execute()
        logger.info("repository: ensure_fresh_user_collection_summary user_id=%s executed successfully", user_id)
    except Exception as exc:
        logger.exception(
            "repository: ensure_fresh_user_collection_summary user_id=%s failed error_type=%s error=%s",
            user_id,
            type(exc).__name__,
            exc,
        )
        raise RuntimeError(f"Failed to ensure fresh summary for user {user_id}") from exc


def refresh_all_stale_user_collection_summaries() -> None:
    """Refresh all user summaries that are marked as stale.
    
    This is used in stale-marking workflows to batch-refresh users after events
    like price ingestion that mark summaries stale.
    
    Raises:
        RuntimeError: If DB function call fails
    """
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")
    
    try:
        supabase.rpc("refresh_all_stale_user_collection_summaries", {}).execute()
        logger.info("repository: refresh_all_stale_user_collection_summaries executed successfully")
    except Exception as exc:
        logger.exception(
            "repository: refresh_all_stale_user_collection_summaries failed error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        raise RuntimeError("Failed to refresh all stale user collection summaries") from exc


def refresh_user_portfolio_summary_and_deltas(
    user_id: UUID,
    snapshot_date: Optional[str] = None,
) -> None:
    """Atomically snapshot current portfolio value and refresh deltas for one user.
    
    This is the primary consistency boundary for user collection summaries.
    When called after holdings mutations, it ensures:
    1) Snapshots current portfolio_value from user_collection_summary
    2) Refreshes all portfolio deltas from history
    3) Both operations remain synchronized
    
    The Supabase DB-side function orchestrates this lightweight atomic sequence.
    It intentionally does not run live recomputation.
    
    Args:
        user_id: UUID of the user whose summary to refresh
        snapshot_date: Optional snapshot date (ISO format YYYY-MM-DD).
                      Defaults to current date in America/Phoenix timezone.
    
    Raises:
        RuntimeError: If DB function call fails
    """
    if supabase is None:
        raise RuntimeError("Supabase client is not initialized")
    
    payload: Dict[str, Any] = {"p_user_id": str(user_id)}
    if snapshot_date:
        payload["p_snapshot_date"] = snapshot_date
    
    try:
        supabase.rpc("refresh_user_portfolio_summary_and_deltas", payload).execute()
        logger.info(
            "repository: refresh_user_portfolio_summary_and_deltas user_id=%s snapshot_date=%s executed successfully",
            user_id,
            snapshot_date or "(default)",
        )
    except Exception as exc:
        logger.exception(
            "repository: refresh_user_portfolio_summary_and_deltas user_id=%s failed error_type=%s error=%s",
            user_id,
            type(exc).__name__,
            exc,
        )
        raise RuntimeError(f"Failed to refresh portfolio summary and deltas for user {user_id}") from exc
