"""Service layer for portfolio summary freshness orchestration."""

from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from backend.db.services.collection_summary_service import (
    run_daily_portfolio_reconciliation_all_users,
)
from backend.db.repositories.user_collection_summary_repository import (
    ensure_fresh_user_collection_summary as repo_ensure_fresh,
    refresh_all_stale_user_collection_summaries as repo_refresh_all_stale,
    refresh_user_collection_summary_live as repo_refresh_live,
    refresh_user_portfolio_summary_and_deltas as repo_refresh_summary_and_deltas,
)

logger = logging.getLogger(__name__)


def ensure_fresh_user_collection_summary(user_id: UUID) -> None:
    """Service wrapper for ensuring summary freshness before reads.
    
    This is called before returning user dashboard/summary data to guarantee
    the summary is fresh (not marked stale).
    
    Args:
        user_id: UUID of the user
        
    Raises:
        RuntimeError: If DB operation fails
    """
    try:
        repo_ensure_fresh(user_id)
        logger.info("collection_freshness.ensure_fresh user_id=%s", user_id)
    except Exception as exc:
        logger.exception(
            "collection_freshness.ensure_fresh user_id=%s failed error=%s",
            user_id,
            exc,
        )
        raise


def refresh_user_collection_summary_live(user_id: UUID) -> None:
    """Service wrapper for live refresh after holdings changes.
    
    Called after user modifies holdings to ensure summary is immediately fresh.
    
    Args:
        user_id: UUID of the user
        
    Raises:
        RuntimeError: If DB operation fails
    """
    try:
        repo_refresh_live(user_id)
        logger.info("collection_freshness.refresh_live user_id=%s", user_id)
    except Exception as exc:
        logger.exception(
            "collection_freshness.refresh_live user_id=%s failed error=%s",
            user_id,
            exc,
        )
        raise


def refresh_all_stale_user_collection_summaries() -> Dict[str, Any]:
    """Service wrapper for batch refreshing all stale user summaries.
    
    Called after price-ingestion events that mark summaries stale.
    Should be invoked in a background job or post-ingestion batch.
    
    Returns:
        Status information about the refresh
        
    Raises:
        RuntimeError: If DB operation fails
    """
    try:
        repo_refresh_all_stale()
        logger.info("collection_freshness.refresh_all_stale executed successfully")
        return {
            "status": "ok",
            "operation": "refresh_all_stale_user_collection_summaries",
        }
    except Exception as exc:
        logger.exception(
            "collection_freshness.refresh_all_stale failed error=%s",
            exc,
        )
        raise


def run_nightly_portfolio_refresh(current_date: str = None) -> Dict[str, Any]:
    """Service wrapper for nightly portfolio refresh orchestration.
    
    Runs the complete nightly portfolio refresh cycle:
    - Refreshes all stale summaries
    - Snapshots daily portfolio history
    
    Args:
        current_date: Optional ISO date string (YYYY-MM-DD)
        
    Returns:
        Status information about the job
        
    Raises:
        RuntimeError: If DB operation fails
    """
    try:
        result = run_daily_portfolio_reconciliation_all_users(current_date=current_date)
        logger.info(
            "collection_freshness.run_nightly_portfolio_refresh completed status=%s snapshot_executed=%s",
            result.get("status"),
            result.get("snapshot_all_users_executed"),
        )
        return {
            "operation": "run_nightly_portfolio_refresh",
            "nightly_refresh_executed": bool(result.get("snapshot_all_users_executed")),
            **result,
        }
    except Exception as exc:
        logger.exception(
            "collection_freshness.run_nightly_portfolio_refresh failed error=%s",
            exc,
        )
        raise


def refresh_user_portfolio_summary_and_deltas(user_id: UUID, snapshot_date: str = None) -> None:
    """Service wrapper for atomic portfolio snapshot + deltas refresh (consistency boundary).
    
    This is the primary consistency boundary for user collection summaries.
    After any holdings mutation, call this function to ensure:
    1) Current portfolio_value is snapshotted to history
    2) All deltas (1d, 7d, 30d, 3m, 6m, 1y, lifetime and their %versions) are refreshed
    
    This lightweight sequence is orchestrated atomically by the DB-side function.
    It intentionally does not invoke live recompute.
    
    Intended usage patterns:
    - After holdings add/remove/modify: mutate_holding() -> this function
    - After portfolio-level import/batch update: refresh wrapper
    - NOT needed after global cron snapshots (those are handled separately)
    
    Args:
        user_id: UUID of the user
        snapshot_date: Optional ISO date string (YYYY-MM-DD). Defaults to today in America/Phoenix.
        
    Raises:
        RuntimeError: If DB operation fails
    """
    try:
        repo_refresh_summary_and_deltas(user_id, snapshot_date)
        logger.info(
            "collection_freshness.refresh_summary_and_deltas user_id=%s snapshot_date=%s",
            user_id,
            snapshot_date or "(default)",
        )
    except Exception as exc:
        logger.exception(
            "collection_freshness.refresh_summary_and_deltas user_id=%s failed error=%s",
            user_id,
            exc,
        )
        raise
