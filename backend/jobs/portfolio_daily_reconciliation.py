"""CLI/job entry point for daily portfolio snapshot + delta reconciliation."""

from __future__ import annotations

import logging

from backend.db.services.collection_summary_service import run_daily_portfolio_reconciliation_all_users


logger = logging.getLogger(__name__)


def run() -> dict:
    """Run daily reconciliation for all users.

    This entry point is intentionally lightweight so an external scheduler/cron can invoke:
    `python -m backend.jobs.portfolio_daily_reconciliation`
    """
    return run_daily_portfolio_reconciliation_all_users()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run()
    logger.info("portfolio_daily_reconciliation.result %s", result)
