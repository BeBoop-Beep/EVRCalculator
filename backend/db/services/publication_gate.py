"""Batch-cohort gate for downstream public-snapshot promotion (Phase 8).

Downstream read models — Cards, Market Dashboard, set pages, rankings, and
simulation-derived publication — must only promote when the day's scrape cohort
contract is satisfied. The authority is ``public.pokemon_scrape_batches``
(migrations 047–049): a batch stamps ``promoted_at`` and flips ``status`` to
``complete`` only when every expected set has a valid Near Mint observation for
the market date (see ``complete_scrape_batch_if_ready``).

Gate decisions:
  * batch ``complete``                         -> allow promotion.
  * batch pending/running/incomplete/failed    -> block; preserve the previous
                                                  good public snapshot.
  * no batch row / batch table not applied     -> allow, but flagged ``ungated``
                                                  so environments without the
                                                  batch system (local/dev, or
                                                  prod before 047–049 is applied)
                                                  keep working unchanged.

An explicit ``override`` promotes without a satisfied cohort for manual
recovery only; it is loudly logged and never the scheduled default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

_GATE_TAG = "[publication-gate]"

# Batch statuses that permit downstream promotion. Only an observation-complete
# cohort (promoted_at stamped) qualifies.
_PROMOTABLE_BATCH_STATUSES = frozenset({"complete"})


@dataclass
class PublicationGateDecision:
    """Outcome of a downstream-publication gate evaluation."""

    allowed: bool
    reason: str
    # True when a real batch verdict drove the decision (vs. ungated fallback).
    gated: bool
    override: bool = False
    market_date: Optional[str] = None
    batch_id: Optional[int] = None
    batch_status: Optional[str] = None
    missing_set_count: Optional[int] = None


def _latest_batch_row(client: Any, market_date: Optional[str]) -> Optional[dict]:
    query = client.table("pokemon_scrape_batches").select(
        "id,market_date,status,promoted_at,missing_set_count,"
        "expected_set_count,succeeded_set_count,failed_set_count"
    )
    if market_date is not None:
        query = query.eq("market_date", market_date)
    result = query.order("market_date", desc=True).limit(1).execute()
    rows = list((result.data if result else []) or [])
    return rows[0] if rows else None


def evaluate_publication_gate(
    client: Any,
    *,
    market_date: Optional[str] = None,
    override: bool = False,
) -> PublicationGateDecision:
    """Decide whether downstream public snapshots may promote for a market date.

    Read-only: never mutates batch or queue state. Requeue/repair of missing
    sets is the scrape batch pipeline's responsibility
    (``requeue_missing_scrape_jobs_for_batch`` / ``run_batch_completion_and_repair``).
    """
    if override:
        logger.warning(
            "%s OVERRIDE ENABLED — promoting downstream snapshots WITHOUT a satisfied "
            "batch cohort contract (manual recovery only). market_date=%s",
            _GATE_TAG,
            market_date or "latest",
        )
        return PublicationGateDecision(
            allowed=True,
            reason="manual override: promoting without a satisfied cohort contract",
            gated=False,
            override=True,
            market_date=market_date,
        )

    try:
        batch = _latest_batch_row(client, market_date)
    except Exception as exc:
        # Batch authority not applied/available — do not block (backward compatible).
        logger.info(
            "%s batch cohort authority unavailable (%s); publishing ungated",
            _GATE_TAG,
            exc,
        )
        return PublicationGateDecision(
            allowed=True,
            reason="batch cohort authority unavailable; publishing ungated",
            gated=False,
            market_date=market_date,
        )

    if not batch:
        logger.info(
            "%s no scrape batch found for market_date=%s; publishing ungated",
            _GATE_TAG,
            market_date or "latest",
        )
        return PublicationGateDecision(
            allowed=True,
            reason="no batch cohort found; publishing ungated",
            gated=False,
            market_date=market_date,
        )

    status = str(batch.get("status") or "").lower()
    resolved_market_date = (
        str(batch.get("market_date")) if batch.get("market_date") else market_date
    )
    missing = batch.get("missing_set_count")
    common = {
        "gated": True,
        "market_date": resolved_market_date,
        "batch_id": batch.get("id"),
        "batch_status": status,
        "missing_set_count": missing,
    }

    if status in _PROMOTABLE_BATCH_STATUSES:
        return PublicationGateDecision(
            allowed=True,
            reason=f"batch {resolved_market_date} is complete; promotion allowed",
            **common,
        )

    logger.warning(
        "%s promotion BLOCKED — batch %s status=%s missing_sets=%s; preserving previous good snapshot",
        _GATE_TAG,
        resolved_market_date,
        status or "unknown",
        missing,
    )
    return PublicationGateDecision(
        allowed=False,
        reason=(
            f"batch {resolved_market_date} status={status or 'unknown'} is not complete; "
            "preserving previous good public snapshot"
        ),
        **common,
    )
