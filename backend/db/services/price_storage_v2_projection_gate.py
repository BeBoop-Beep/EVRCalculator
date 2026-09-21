"""Readiness contract between completed scrapes and Price Storage V2 serving.

Public canonical card prices now resolve through ``card_variant_price_current_v2``.
Therefore a complete scrape batch is necessary but not sufficient for safe
post-scrape publication: every completed scrape set must also have a current
``price_storage_v2_shadow_queue`` row whose source completion timestamp covers
the scrape job completion that produced the target market date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


REASON_READY = "price_projection_ready"
REASON_NOT_READY = "price_projection_not_ready"
REASON_AUTHORITY_UNAVAILABLE = "price_projection_authority_unavailable"
REASON_NO_COMPLETED_SCRAPES = "price_projection_no_completed_scrapes"


def _parse_ts(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class PriceProjectionDecision:
    ready: bool
    market_date: str
    reason_code: str
    expected_set_count: int = 0
    complete_set_count: int = 0
    pending_set_ids: List[str] = field(default_factory=list)
    failed_set_ids: List[str] = field(default_factory=list)
    terminal_failed_set_ids: List[str] = field(default_factory=list)
    missing_set_ids: List[str] = field(default_factory=list)
    stale_source_set_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ready": self.ready,
            "market_date": self.market_date,
            "reason_code": self.reason_code,
            "expected_set_count": self.expected_set_count,
            "complete_set_count": self.complete_set_count,
            "pending_set_count": len(self.pending_set_ids),
            "failed_set_count": len(self.failed_set_ids),
            "terminal_failed_set_count": len(self.terminal_failed_set_ids),
            "missing_set_count": len(self.missing_set_ids),
            "stale_source_set_count": len(self.stale_source_set_ids),
            "pending_set_ids": self.pending_set_ids[:25],
            "failed_set_ids": self.failed_set_ids[:25],
            "terminal_failed_set_ids": self.terminal_failed_set_ids[:25],
            "missing_set_ids": self.missing_set_ids[:25],
            "stale_source_set_ids": self.stale_source_set_ids[:25],
            "error": self.error,
        }


def evaluate_price_projection_gate(client: Any, market_date: str) -> PriceProjectionDecision:
    day = str(market_date or "")[:10]
    try:
        scrape_rows = list(
            client.table("scrape_jobs")
            .select("set_id,completed_at")
            .eq("market_date", day)
            .eq("status", "completed")
            .execute().data or []
        )
        queue_rows = list(
            client.table("price_storage_v2_shadow_queue")
            .select("set_id,status,attempts,last_error,source_completed_at,completed_at,updated_at")
            .eq("market_date", day)
            .execute().data or []
        )
    except Exception as exc:
        return PriceProjectionDecision(
            ready=False,
            market_date=day,
            reason_code=REASON_AUTHORITY_UNAVAILABLE,
            error=f"{type(exc).__name__}: {exc}",
        )

    latest_scrape_by_set: Dict[str, datetime] = {}
    for row in scrape_rows:
        set_id = str(row.get("set_id") or "")
        completed_at = _parse_ts(row.get("completed_at"))
        if not set_id or completed_at is None:
            continue
        previous = latest_scrape_by_set.get(set_id)
        if previous is None or completed_at > previous:
            latest_scrape_by_set[set_id] = completed_at

    expected_ids = sorted(latest_scrape_by_set)
    if not expected_ids:
        return PriceProjectionDecision(
            ready=False,
            market_date=day,
            reason_code=REASON_NO_COMPLETED_SCRAPES,
        )

    queue_by_set = {
        str(row.get("set_id")): row
        for row in queue_rows
        if row.get("set_id")
    }
    complete: List[str] = []
    pending: List[str] = []
    failed: List[str] = []
    terminal_failed: List[str] = []
    missing: List[str] = []
    stale_source: List[str] = []

    for set_id in expected_ids:
        row = queue_by_set.get(set_id)
        if row is None:
            missing.append(set_id)
            continue
        status = str(row.get("status") or "").strip().lower()
        source_completed_at = _parse_ts(row.get("source_completed_at"))
        if source_completed_at is None or source_completed_at < latest_scrape_by_set[set_id]:
            stale_source.append(set_id)
            continue
        if status == "complete":
            complete.append(set_id)
        elif status == "failed":
            failed.append(set_id)
            try:
                attempts = int(row.get("attempts") or 0)
            except (TypeError, ValueError):
                attempts = 0
            if attempts >= 5:
                terminal_failed.append(set_id)
        else:
            pending.append(set_id)

    ready = len(complete) == len(expected_ids)
    return PriceProjectionDecision(
        ready=ready,
        market_date=day,
        reason_code=REASON_READY if ready else REASON_NOT_READY,
        expected_set_count=len(expected_ids),
        complete_set_count=len(complete),
        pending_set_ids=pending,
        failed_set_ids=failed,
        terminal_failed_set_ids=terminal_failed,
        missing_set_ids=missing,
        stale_source_set_ids=stale_source,
    )


def advance_price_projection_once(
    client: Any, market_date: str, *, process_limit: int = 20
) -> Dict[str, Any]:
    """Idempotently enqueue the target cohort and process one bounded queue chunk."""
    day = str(market_date or "")[:10]
    enqueue = client.rpc(
        "enqueue_price_storage_v2_completed_scrape_jobs",
        {"p_market_date": day, "p_limit": 1000},
    ).execute()
    before = evaluate_price_projection_gate(client, day)
    process_result = None
    if not before.ready and before.reason_code != REASON_AUTHORITY_UNAVAILABLE:
        processed = client.rpc(
            "process_price_storage_v2_shadow_queue",
            {"p_limit": max(1, min(int(process_limit), 20))},
        ).execute()
        process_result = getattr(processed, "data", None)
    after = evaluate_price_projection_gate(client, day)
    return {
        "market_date": day,
        "enqueue_result": getattr(enqueue, "data", None),
        "process_result": process_result,
        "before": before.to_dict(),
        "after": after.to_dict(),
    }
