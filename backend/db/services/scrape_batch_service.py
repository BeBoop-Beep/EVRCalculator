"""Batch completion + cohort repair (Phase 6).

When the queue becomes idle, the batch is checked for cohort completeness against
valid Near Mint observations for the target Arizona market date:

  * If complete, the batch is marked ``complete`` and ``promoted_at`` is stamped —
    this is the gate downstream snapshot promotion should honour.
  * If incomplete, only the missing/invalid sets are requeued (bounded by
    per-set attempt limits), the batch is marked ``incomplete``, and an
    actionable alert is queued. The previous complete market date stays public.

The database is the authority. Alerts are best-effort and never affect batch
state.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.alerts.scrape_alerts import alert_batch_incomplete
from backend.db.repositories.scrape_jobs_repository import (
    complete_scrape_batch_if_ready,
    count_active_scrape_jobs,
    get_active_batch,
    get_scrape_missing_sets,
    requeue_missing_scrape_jobs_for_batch,
    requeue_unreconciled_retryable_scrape_jobs_for_batch,
)

logger = logging.getLogger(__name__)

_SVC_TAG = "[scrape-batch]"


def run_batch_completion_and_repair(
    market_date: Optional[str] = None,
    *,
    repair: bool = True,
) -> Dict[str, Any]:
    """Evaluate the target batch; requeue missing sets and alert if incomplete.

    Returns a summary dict. Safe to call repeatedly (idempotent): a complete batch
    is returned unchanged, and repair only reopens failed/absent sets that still
    have attempts remaining.
    """
    batch = get_active_batch(market_date)
    if not batch:
        logger.info("%s no batch found for market_date=%s", _SVC_TAG, market_date or "latest")
        return {"ok": False, "reason": "no_batch"}

    batch_id = batch["id"]
    resolved_market_date = str(batch["market_date"])

    active = count_active_scrape_jobs(batch_id)
    if active > 0:
        logger.info(
            "%s batch %s (%s) still has %s active job(s); skipping completion check",
            _SVC_TAG, batch_id, resolved_market_date, active,
        )
        return {"ok": True, "batch_id": batch_id, "status": "running", "active": active}

    # Queue is idle for this batch — repair missing sets before declaring status.
    observation_missing_requeued = 0
    unreconciled_run_requeued = 0
    deterministic_blocked = 0
    requeued = 0
    if repair:
        # Run reconciliation repair first. A failed job may also be observation-
        # missing; reopening it here preserves its diagnostic error fields and
        # makes the later observation repair naturally skip the now-active row.
        run_repair = requeue_unreconciled_retryable_scrape_jobs_for_batch(batch_id)
        unreconciled_run_requeued = int(run_repair.get("unreconciledRunRequeued") or 0)
        deterministic_blocked = int(run_repair.get("deterministicBlocked") or 0)
        observation_missing_requeued = requeue_missing_scrape_jobs_for_batch(batch_id)
        requeued = observation_missing_requeued + unreconciled_run_requeued
        if requeued > 0:
            logger.warning(
                "%s cohort repair requeued %s set(s) for batch %s (%s)",
                _SVC_TAG, requeued, batch_id, resolved_market_date,
            )
            # New work exists; batch is still running. Let the worker drain it.
            return {
                "ok": True,
                "batch_id": batch_id,
                "status": "running",
                "requeued": requeued,
                "observationMissingRequeued": observation_missing_requeued,
                "unreconciledRunRequeued": unreconciled_run_requeued,
                "deterministicBlocked": deterministic_blocked,
            }

    # No requeueable work remains — evaluate completeness authoritatively.
    completion = complete_scrape_batch_if_ready(batch_id)
    status = completion.get("status")
    missing_count = int(completion.get("missing_set_count") or 0)

    if status == "complete":
        logger.info(
            "%s batch %s (%s) is COMPLETE and promoted", _SVC_TAG, batch_id, resolved_market_date
        )
    else:
        missing_sets = get_scrape_missing_sets(resolved_market_date)
        logger.error(
            "%s batch %s (%s) is INCOMPLETE: %s set(s) missing; promotion blocked",
            _SVC_TAG, batch_id, resolved_market_date, missing_count,
        )
        alert_batch_incomplete(
            batch_id,
            resolved_market_date,
            missing_set_count=missing_count,
            missing_sets=missing_sets,
            succeeded_set_count=completion.get("succeeded_set_count"),
            failed_set_count=completion.get("failed_set_count"),
        )

    return {
        "ok": True,
        "batch_id": batch_id,
        "market_date": resolved_market_date,
        "status": status,
        "missing_set_count": missing_count,
        "requeued": requeued,
        "observationMissingRequeued": observation_missing_requeued,
        "unreconciledRunRequeued": unreconciled_run_requeued,
        "deterministicBlocked": deterministic_blocked,
        "promoted": completion.get("promoted", False),
    }
