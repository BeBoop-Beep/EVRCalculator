"""Background job scheduler for portfolio maintenance tasks."""

from __future__ import annotations

import logging
from datetime import time
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import APScheduler, but make it optional
try:
    from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
    from apscheduler.triggers.cron import CronTrigger  # type: ignore
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False
    logger.warning(
        "scheduler_service: APScheduler not installed. Background scheduling unavailable. "
        "Install with: pip install apscheduler. Or invoke nightly job via manual endpoint/cron."
    )


# Global scheduler instance
_scheduler: Optional[object] = None


def initialize_scheduler(nightly_refresh_time: time = time(3, 0, 0)) -> Optional[object]:
    """
    Initialize and start the background scheduler.
    
    Args:
        nightly_refresh_time: Time of day to run nightly refresh (default 3:00 AM)
        
    Returns:
        The initialized BackgroundScheduler instance, or None if APScheduler unavailable
        
    Raises:
        RuntimeError: If scheduler initialization fails
    """
    global _scheduler
    
    if _scheduler is not None:
        logger.warning("scheduler_service: scheduler already initialized")
        return _scheduler
    
    if not HAS_APSCHEDULER:
        logger.info(
            "scheduler_service: APScheduler not available. Automatic scheduling disabled. "
            "Use external cron/scheduler to invoke: POST /jobs/portfolio/daily-reconciliation "
            "or: python -m backend.jobs.portfolio_daily_reconciliation"
        )
        return None
    
    try:
        _scheduler = BackgroundScheduler()
        
        # Add nightly portfolio refresh job
        hour = nightly_refresh_time.hour
        minute = nightly_refresh_time.minute
        second = nightly_refresh_time.second
        
        _scheduler.add_job(
            _run_nightly_portfolio_refresh,
            CronTrigger(hour=hour, minute=minute, second=second),
            id="nightly_portfolio_refresh",
            name="Nightly Portfolio Refresh",
            replace_existing=True,
            max_instances=1,  # Prevent concurrent runs
        )
        
        _scheduler.start()
        logger.info(
            "scheduler_service: scheduler started with nightly refresh at %02d:%02d:%02d",
            hour,
            minute,
            second,
        )
        return _scheduler
    
    except Exception as exc:
        logger.exception("scheduler_service: failed to initialize scheduler error=%s", exc)
        raise RuntimeError("Failed to initialize background scheduler") from exc


def stop_scheduler() -> None:
    """Stop the background scheduler."""
    global _scheduler
    
    if _scheduler is None:
        logger.debug("scheduler_service: no scheduler to stop")
        return
    
    try:
        _scheduler.shutdown(wait=True)
        _scheduler = None
        logger.info("scheduler_service: scheduler stopped")
    except Exception as exc:
        logger.exception("scheduler_service: error stopping scheduler error=%s", exc)


def get_scheduler() -> Optional[object]:
    """Get the current scheduler instance, if running."""
    global _scheduler
    return _scheduler


def _run_nightly_portfolio_refresh() -> None:
    """Internal function called by scheduler to run nightly refresh."""
    from backend.db.services.collection_summary_service import (
        run_daily_portfolio_reconciliation_all_users,
    )
    
    try:
        logger.info("scheduler_service: nightly_refresh_job started")
        result = run_daily_portfolio_reconciliation_all_users()
        logger.info("scheduler_service: nightly_refresh_job completed result=%s", result)
    except Exception as exc:
        logger.exception(
            "scheduler_service: nightly_refresh_job failed error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        # Don't raise - scheduler should continue even if one job fails
