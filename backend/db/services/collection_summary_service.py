"""Service layer orchestration for collection summary metrics."""

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from backend.calculations.collection_summary import (
    calculate_cards_count,
    calculate_graded_count,
    calculate_portfolio_value,
    calculate_sealed_count,
    calculate_summary,
)
from backend.db.repositories.user_collection_summary_repository import (
    has_stale_user_collection_summary_rows,
    load_user_collection_for_summary,
    load_user_collection_summary_snapshot,
    refresh_user_collection_deltas,
    snapshot_all_user_portfolio_history,
    snapshot_user_portfolio_history,
    upsert_user_collection_summary,
)
from backend.models.collection_summary_models import CollectionSummary


logger = logging.getLogger(__name__)

DELTA_ABSOLUTE_FIELDS = (
    "portfolio_delta_1d",
    "portfolio_delta_7d",
    "portfolio_delta_3m",
    "portfolio_delta_6m",
    "portfolio_delta_1y",
    "portfolio_delta_lifetime",
)

DELTA_PERCENT_FIELDS = (
    "portfolio_delta_pct_1d",
    "portfolio_delta_pct_7d",
    "portfolio_delta_pct_3m",
    "portfolio_delta_pct_6m",
    "portfolio_delta_pct_1y",
    "portfolio_delta_pct_lifetime",
)


def _to_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _to_int(value: Any, fallback: int = 0) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _to_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y"}:
            return True
        if normalized in {"0", "false", "f", "no", "n"}:
            return False
    return None


def _to_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_user_collection_summary_snapshot(user_id: UUID) -> Dict[str, Any]:
    """Load and normalize the precomputed summary row for public summary reads."""
    row = load_user_collection_summary_snapshot(user_id)
    row_found = isinstance(row, dict) and bool(row)
    normalized_row = row or {}

    summary = {
        "portfolio_value": _to_float(normalized_row.get("portfolio_value"), 0.0),
        "cards_count": _to_int(normalized_row.get("cards_count"), 0),
        "sealed_count": _to_int(normalized_row.get("sealed_count"), 0),
        "graded_count": _to_int(normalized_row.get("graded_count"), 0),
        "computed_at": normalized_row.get("computed_at"),
        "is_stale": _to_optional_bool(normalized_row.get("is_stale")),
        "row_found": row_found,
    }

    for field_name in DELTA_ABSOLUTE_FIELDS:
        summary[field_name] = _to_float(normalized_row.get(field_name), 0.0)

    for field_name in DELTA_PERCENT_FIELDS:
        summary[field_name] = _to_optional_float(normalized_row.get(field_name))

    logger.info(
        "public_collection.summary_snapshot user_id=%s row_found=%s portfolio_value=%s cards_count=%s sealed_count=%s graded_count=%s computed_at=%s is_stale=%s fallback_used=%s",
        user_id,
        row_found,
        summary["portfolio_value"],
        summary["cards_count"],
        summary["sealed_count"],
        summary["graded_count"],
        summary["computed_at"],
        summary["is_stale"],
        not row_found,
    )

    return summary


def get_user_collection_summary(user_id: UUID) -> CollectionSummary:
    """Load holdings payloads, compute metrics, and return CollectionSummary."""
    payload = load_user_collection_for_summary(user_id)

    user_card_holdings = payload.get("user_card_holdings", [])
    user_sealed_product_holdings = payload.get("user_sealed_product_holdings", [])
    user_graded_card_holdings = payload.get("user_graded_card_holdings", [])

    portfolio_value = calculate_portfolio_value(
        user_card_holdings=user_card_holdings,
        user_sealed_product_holdings=user_sealed_product_holdings,
        user_graded_card_holdings=user_graded_card_holdings,
    )
    cards_count = calculate_cards_count(user_card_holdings=user_card_holdings)
    sealed_count = calculate_sealed_count(user_sealed_product_holdings=user_sealed_product_holdings)
    graded_count = calculate_graded_count(user_graded_card_holdings=user_graded_card_holdings)

    logger.warning(
        "[portfolio-debug] summary totals user_id=%s raw_card_rows=%s sealed_rows=%s graded_rows=%s portfolio_value=%s cards_count=%s sealed_count=%s graded_count=%s",
        user_id,
        len(user_card_holdings),
        len(user_sealed_product_holdings),
        len(user_graded_card_holdings),
        portfolio_value,
        cards_count,
        sealed_count,
        graded_count,
    )

    return calculate_summary(
        portfolio_value=portfolio_value,
        cards_count=cards_count,
        sealed_count=sealed_count,
        graded_count=graded_count,
    )


def refresh_user_summary_with_history_and_deltas(user_id: UUID) -> Dict[str, Any]:
    """Refresh summary and then execute portfolio snapshot/delta DB functions for one user.

    Orchestration order (Phase 1 contract):
    1) recompute summary and persist user_collection_summary
    2) snapshot_user_portfolio_history(user_id)
    3) refresh_user_collection_deltas(user_id)
    4) read updated summary row and return
    """
    try:
        computed = get_user_collection_summary(user_id)
        upsert_user_collection_summary(user_id, computed.to_dict())
    except Exception as exc:
        logger.exception(
            "collection_summary.refresh_orchestration summary_refresh_failed user_id=%s error_type=%s error=%s",
            user_id,
            type(exc).__name__,
            exc,
        )
        raise RuntimeError(f"Failed to refresh summary for user {user_id}") from exc

    try:
        snapshot_user_portfolio_history(user_id)
    except Exception as exc:
        logger.exception(
            "collection_summary.refresh_orchestration snapshot_failed user_id=%s error_type=%s error=%s",
            user_id,
            type(exc).__name__,
            exc,
        )
        raise RuntimeError(f"Failed to snapshot portfolio history for user {user_id}") from exc

    try:
        refresh_user_collection_deltas(user_id)
    except Exception as exc:
        logger.exception(
            "collection_summary.refresh_orchestration delta_refresh_failed user_id=%s error_type=%s error=%s",
            user_id,
            type(exc).__name__,
            exc,
        )
        raise RuntimeError(f"Failed to refresh portfolio deltas for user {user_id}") from exc

    refreshed_snapshot = get_user_collection_summary_snapshot(user_id)
    logger.info(
        "collection_summary.refresh_orchestration success user_id=%s portfolio_value=%s cards_count=%s sealed_count=%s graded_count=%s",
        user_id,
        refreshed_snapshot.get("portfolio_value"),
        refreshed_snapshot.get("cards_count"),
        refreshed_snapshot.get("sealed_count"),
        refreshed_snapshot.get("graded_count"),
    )
    return refreshed_snapshot


def run_daily_portfolio_reconciliation_all_users() -> Dict[str, Any]:
    """Backend-invokable daily reconciliation entry point for all users."""
    if has_stale_user_collection_summary_rows():
        raise RuntimeError(
            "Daily portfolio reconciliation aborted: user_collection_summary contains stale rows"
        )

    try:
        snapshot_all_user_portfolio_history()
    except Exception as exc:
        logger.exception(
            "collection_summary.daily_reconciliation snapshot_all_failed error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        raise RuntimeError("Failed to snapshot all user portfolio history") from exc

    try:
        refresh_user_collection_deltas()
    except Exception as exc:
        logger.exception(
            "collection_summary.daily_reconciliation delta_refresh_all_failed error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        raise RuntimeError("Failed to refresh portfolio deltas for all users") from exc

    logger.info("collection_summary.daily_reconciliation success")
    return {
        "status": "ok",
        "summary_source_verified": True,
        "snapshot_all_users_executed": True,
        "delta_refresh_all_users_executed": True,
    }
