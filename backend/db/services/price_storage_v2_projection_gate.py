"""Readiness contract between completed scrapes and Price Storage V2 serving.

Public canonical card prices now resolve through ``card_variant_price_current_v2``.
Therefore a complete scrape batch is necessary but not sufficient for safe
post-scrape publication: every completed scrape set must also have a current
``price_storage_v2_shadow_queue`` row whose source completion timestamp covers
the scrape job completion that produced the target market date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from backend.db.clients.supabase_client import create_service_role_client
from backend.scripts.snapshot_query_retry import run_snapshot_operation_with_retry


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


PROJECTION_QUEUE_TABLE = "price_storage_v2_shadow_queue"
PROJECTION_STALE_PROCESSING_SECONDS = 20 * 60


def _evaluate_projection_with_retry(
    client: Any,
    market_date: str,
    *,
    client_factory: Callable[[], Any],
    max_attempts: int = 3,
) -> PriceProjectionDecision:
    """Retry only authority-unavailable readiness reads with fresh clients."""
    decision = evaluate_price_projection_gate(client, market_date)
    attempts = max(1, min(int(max_attempts), 3))
    for _attempt in range(2, attempts + 1):
        if decision.reason_code != REASON_AUTHORITY_UNAVAILABLE:
            break
        decision = evaluate_price_projection_gate(client_factory(), market_date)
    return decision


def _reconcile_stale_projection_claims(
    market_date: str,
    *,
    client_factory: Callable[[], Any],
    stale_seconds: int = PROJECTION_STALE_PROCESSING_SECONDS,
) -> None:
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=max(60, int(stale_seconds)))
    ).isoformat()

    run_snapshot_operation_with_retry(
        lambda op_client: op_client.table(PROJECTION_QUEUE_TABLE)
        .update(
            {
                "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "last_error": "stale staged projection lease reclaimed",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("market_date", market_date)
        .eq("status", "processing")
        .lt("started_at", cutoff)
        .execute(),
        operation_name="price-storage-v2:reconcile-stale-staged-claims",
        max_attempts=3,
        client_factory=client_factory,
    )


def _claim_projection_job(
    market_date: str,
    *,
    client_factory: Callable[[], Any],
) -> Optional[Dict[str, Any]]:
    """Optimistically claim the oldest retryable job for one market date."""

    def _claim(op_client: Any) -> Optional[Dict[str, Any]]:
        rows = list(
            op_client.table(PROJECTION_QUEUE_TABLE)
            .select("id,set_id,market_date,status,attempts,started_at")
            .eq("market_date", market_date)
            .in_("status", ["pending", "failed"])
            .lt("attempts", 5)
            .order("id")
            .limit(1)
            .execute().data
            or []
        )
        if not rows:
            return None

        candidate = dict(rows[0])
        old_status = str(candidate.get("status") or "")
        old_attempts = int(candidate.get("attempts") or 0)
        now = datetime.now(timezone.utc).isoformat()
        claimed = list(
            op_client.table(PROJECTION_QUEUE_TABLE)
            .update(
                {
                    "status": "processing",
                    "attempts": old_attempts + 1,
                    "started_at": now,
                    "completed_at": None,
                    "last_error": None,
                    "updated_at": now,
                }
            )
            .eq("id", candidate["id"])
            .eq("status", old_status)
            .eq("attempts", old_attempts)
            .execute().data
            or []
        )
        if not claimed:
            return None
        return dict(claimed[0])

    # A racing pg_cron worker can win the optimistic update. In that case,
    # retry the claim with a fresh client so another pending row can proceed.
    for _ in range(3):
        claimed = run_snapshot_operation_with_retry(
            _claim,
            operation_name="price-storage-v2:claim-staged-job",
            max_attempts=3,
            client_factory=client_factory,
        )
        if claimed is not None:
            return claimed
    return None


def _finish_projection_job(
    job: Dict[str, Any],
    *,
    status: str,
    last_error: Optional[str],
    client_factory: Callable[[], Any],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    job_id = job.get("id")
    attempts = int(job.get("attempts") or 0)

    run_snapshot_operation_with_retry(
        lambda op_client: op_client.table(PROJECTION_QUEUE_TABLE)
        .update(
            {
                "status": status,
                "completed_at": now,
                "last_error": last_error,
                "updated_at": now,
            }
        )
        .eq("id", job_id)
        .eq("status", "processing")
        .eq("attempts", attempts)
        .execute(),
        operation_name=f"price-storage-v2:finish-staged-job:{status}",
        set_id=str(job.get("set_id") or ""),
        max_attempts=3,
        client_factory=client_factory,
    )


def _process_projection_job_staged(
    job: Dict[str, Any],
    *,
    client_factory: Callable[[], Any],
) -> Dict[str, Any]:
    """Run one claimed queue job with each expensive stage in its own transaction."""
    set_id = str(job.get("set_id") or "")
    market_date = str(job.get("market_date") or "")[:10]
    stages = (
        (
            "sync_price_storage_v2_set_date",
            {"p_set_id": set_id, "p_market_date": market_date},
        ),
        (
            "sync_price_observation_ranges_v2_set_date",
            {"p_set_id": set_id, "p_market_date": market_date},
        ),
        (
            "sync_pokemon_market_price_intervals_v2_shadow_set_from_date",
            {"p_set_id": set_id, "p_market_date": market_date},
        ),
        (
            "refresh_pokemon_canonical_card_market_prices_latest_for_set",
            {"target_set_id": set_id},
        ),
    )

    completed_stages: List[str] = []
    try:
        for rpc_name, params in stages:
            run_snapshot_operation_with_retry(
                lambda op_client, name=rpc_name, args=params: op_client.rpc(
                    name, args
                ).execute(),
                operation_name=f"price-storage-v2:staged:{rpc_name}",
                set_id=set_id,
                max_attempts=3,
                client_factory=client_factory,
            )
            completed_stages.append(rpc_name)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:2000]
        _finish_projection_job(
            job,
            status="failed",
            last_error=error,
            client_factory=client_factory,
        )
        return {
            "id": job.get("id"),
            "set_id": set_id,
            "status": "failed",
            "completed_stages": completed_stages,
            "error_type": type(exc).__name__,
        }

    _finish_projection_job(
        job,
        status="complete",
        last_error=None,
        client_factory=client_factory,
    )
    return {
        "id": job.get("id"),
        "set_id": set_id,
        "status": "complete",
        "completed_stages": completed_stages,
    }


def _process_projection_jobs_staged(
    market_date: str,
    *,
    process_limit: int,
    client_factory: Callable[[], Any],
) -> Dict[str, Any]:
    limit = max(1, min(int(process_limit), 20))
    reports: List[Dict[str, Any]] = []
    for _ in range(limit):
        job = _claim_projection_job(market_date, client_factory=client_factory)
        if job is None:
            break
        reports.append(
            _process_projection_job_staged(job, client_factory=client_factory)
        )
    return {
        "processed": len(reports),
        "completed": sum(1 for row in reports if row.get("status") == "complete"),
        "failed": sum(1 for row in reports if row.get("status") == "failed"),
        "jobs": reports,
    }


def advance_price_projection_once(
    client: Any,
    market_date: str,
    *,
    process_limit: int = 20,
    client_factory: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    """Idempotently enqueue and advance a bounded Price Storage V2 cohort.

    Queue jobs are processed by an application-level staged worker: the four
    expensive projection stages run in separate database transactions, so their
    cumulative runtime can no longer trip one statement timeout and roll the
    entire job back. Every stage retains the existing three-attempt transient
    retry policy with a fresh service-role client. Deterministic failures mark
    only that claimed set failed; later sets continue instead of starving
    behind one poison row.
    """
    day = str(market_date or "")[:10]
    factory = client_factory or create_service_role_client

    enqueue = run_snapshot_operation_with_retry(
        lambda op_client: op_client.rpc(
            "enqueue_price_storage_v2_completed_scrape_jobs",
            {"p_market_date": day, "p_limit": 1000},
        ).execute(),
        operation_name="price-storage-v2:enqueue-completed-scrapes",
        max_attempts=3,
        client_factory=factory,
    )

    _reconcile_stale_projection_claims(day, client_factory=factory)
    before = _evaluate_projection_with_retry(
        client, day, client_factory=factory
    )

    process_result = None
    if not before.ready and before.reason_code != REASON_AUTHORITY_UNAVAILABLE:
        process_result = _process_projection_jobs_staged(
            day,
            process_limit=process_limit,
            client_factory=factory,
        )

    after = _evaluate_projection_with_retry(
        client, day, client_factory=factory
    )
    return {
        "market_date": day,
        "enqueue_result": getattr(enqueue, "data", None),
        "process_result": process_result,
        "before": before.to_dict(),
        "after": after.to_dict(),
    }
