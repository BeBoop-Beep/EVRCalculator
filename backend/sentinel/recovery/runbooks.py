"""Initial allowlisted recovery runbooks for inDex Sentinel P6.

Only bounded, deterministic failure signatures are eligible:
1. market.freshness / market_publication_stale
2. market.freshness / market_snapshot_date_divergence
3. pricing.multi_source.run_freshness / DAILY_RUN_STALE_OR_INCOMPLETE
4. scrape.queue_leases / scrape_job_lease_expired

All other incidents remain observation/escalation only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Optional

from backend.sentinel.checks.authorities import (
    check_market_freshness,
    check_scrape_queue_leases,
)
from backend.sentinel.models import CheckOutcome, IncidentRecord
from backend.sentinel.recovery.engine import (
    RecoveryContext,
    RecoveryDecision,
    RecoveryExecution,
    RecoveryRegistry,
    RecoveryRunbook,
)
from backend.sentinel.registry import CheckContext


PHOENIX = timezone(timedelta(hours=-7), "America/Phoenix")

PUBLICATION_RUNBOOK = "publish_post_scrape_if_needed_v1"
PUBLICATION_DIVERGENCE_RUNBOOK = "reconcile_market_snapshot_divergence_v1"
PRICING_RUNBOOK = "resume_daily_multi_source_pricing_v1"
LEASE_RUNBOOK = "reconcile_stale_scrape_leases_v1"


def _default_client() -> Any:
    from backend.db.clients.supabase_client import supabase

    return supabase


def _valid_market_date(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    if parsed.strftime("%Y-%m-%d") != text:
        return None
    return text


def _check_context(context: RecoveryContext) -> CheckContext:
    return CheckContext(now=context.now, runner_identity=context.runner_identity)


def _default_pricing_runner(market_date: str) -> dict:
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env.setdefault(
        "EVR_PRICING_STATE_DIR",
        "/home/ubuntu/state/multi_source_pricing",
    )
    command = [
        sys.executable,
        "-m",
        "backend.scripts.run_daily_multi_source_card_pricing",
        "--market-date",
        market_date,
        "--json",
        "--resume",
        "--no-frontend-env-fallback",
    ]
    completed = subprocess.run(
        command,
        cwd=str(repo_root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60 * 60,
        check=False,
    )
    return {
        "returncode": int(completed.returncode),
        "status": "complete" if completed.returncode == 0 else "not_complete",
    }


def _pricing_run_freshness_check(
    context: RecoveryContext,
    *,
    client: Any,
):
    from backend.pricing_pipeline import health as pricing_health

    snapshot = pricing_health.gather(client, context.now)
    for result in pricing_health.sentinel_results(snapshot):
        if result.check_key == "pricing.multi_source.run_freshness":
            return result
    raise RuntimeError("pricing run freshness check was not produced")


def build_safe_recovery_registry(
    *,
    client: Any = None,
    publish_if_needed_fn: Optional[Callable[..., dict]] = None,
    gate_evaluator: Optional[Callable[..., Any]] = None,
    market_freshness_checker: Optional[Callable[..., Any]] = None,
    lease_reconciler: Optional[Callable[[], int]] = None,
    lease_checker: Optional[Callable[..., Any]] = None,
    pricing_runner: Optional[Callable[[str], dict]] = None,
    pricing_checker: Optional[Callable[..., Any]] = None,
) -> RecoveryRegistry:
    """Build the P6 exact-match recovery allowlist.

    Dependencies are injectable for deterministic tests. Defaults call only the
    repository's existing gated/idempotent publication wrapper and lease RPC.
    """
    resolved_client = client if client is not None else _default_client()

    if publish_if_needed_fn is None:
        from backend.scripts.publish_post_scrape_if_needed import publish_if_needed

        publish_if_needed_fn = publish_if_needed
    if gate_evaluator is None:
        from backend.db.services.publication_gate import evaluate_publication_gate

        gate_evaluator = evaluate_publication_gate
    if market_freshness_checker is None:
        market_freshness_checker = check_market_freshness
    if lease_reconciler is None:
        from backend.db.repositories.scrape_jobs_repository import reconcile_stale_scrape_jobs

        lease_reconciler = reconcile_stale_scrape_jobs
    if lease_checker is None:
        lease_checker = check_scrape_queue_leases
    if pricing_runner is None:
        pricing_runner = _default_pricing_runner
    if pricing_checker is None:
        pricing_checker = _pricing_run_freshness_check

    registry = RecoveryRegistry()

    def publication_precondition(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryDecision:
        market_date = _valid_market_date(incident.authority_identity)
        if market_date is None:
            return RecoveryDecision.block(
                "publication_recovery_market_date_invalid",
                authority_identity=incident.authority_identity,
            )

        live = market_freshness_checker(
            _check_context(context), client=resolved_client
        )
        if live.outcome is CheckOutcome.HEALTHY:
            return RecoveryDecision.block(
                "publication_failure_already_cleared", market_date=market_date
            )
        if (
            live.failure_code != incident.failure_code
            or live.failure_code not in {"market_publication_stale", "market_snapshot_date_divergence"}
            or live.authority_identity != incident.authority_identity
        ):
            return RecoveryDecision.block(
                "publication_failure_signature_changed",
                incident_failure=incident.failure_code,
                live_failure=live.failure_code,
                incident_authority=incident.authority_identity,
                live_authority=live.authority_identity,
            )

        decision = gate_evaluator(
            resolved_client, market_date=market_date, override=False
        )
        allowed = bool(getattr(decision, "allowed", False))
        reason_code = str(getattr(decision, "reason_code", "") or "")
        if not allowed or reason_code != "allowed_complete":
            return RecoveryDecision.block(
                "publication_batch_gate_not_complete",
                market_date=market_date,
                gate_allowed=allowed,
                gate_reason_code=reason_code,
                batch_id=getattr(decision, "batch_id", None),
                batch_status=getattr(decision, "batch_status", None),
                missing_set_count=getattr(decision, "missing_set_count", None),
            )
        return RecoveryDecision.allow(
            market_date=market_date,
            gate_reason_code=reason_code,
            batch_id=getattr(decision, "batch_id", None),
        )

    def publication_execute(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryExecution:
        del context
        market_date = _valid_market_date(incident.authority_identity)
        if market_date is None:
            return RecoveryExecution.blocked(
                result={"status": "invalid_market_date"}
            )
        result = dict(
            publish_if_needed_fn(market_date, client=resolved_client) or {}
        )
        status = str(result.get("status") or "")
        if status == "published":
            return RecoveryExecution.succeeded(
                result=result, mutation_performed=True
            )
        if status == "noop_already_current":
            return RecoveryExecution.succeeded(
                result=result, mutation_performed=False
            )
        if status in {
            "noop_batch_not_complete",
            "noop_already_running",
            "noop_currency_unknown",
            "noop_already_running",
            "gate_authority_unavailable",
            "gate_invalid_contract",
            "invalid_market_date",
        }:
            return RecoveryExecution.blocked(result=result)
        return RecoveryExecution.failed(result=result)

    def publication_verify(incident: IncidentRecord, context: RecoveryContext):
        del incident
        return market_freshness_checker(
            _check_context(context), client=resolved_client
        )

    registry.register(
        RecoveryRunbook(
            key=PUBLICATION_RUNBOOK,
            version="1",
            check_key="market.freshness",
            failure_code="market_publication_stale",
            precondition=publication_precondition,
            execute=publication_execute,
            verify=publication_verify,
            max_attempts=1,
            cooldown_seconds=60 * 60,
        )
    )

    registry.register(
        RecoveryRunbook(
            key=PUBLICATION_DIVERGENCE_RUNBOOK,
            version="1",
            check_key="market.freshness",
            failure_code="market_snapshot_date_divergence",
            precondition=publication_precondition,
            execute=publication_execute,
            verify=publication_verify,
            max_attempts=1,
            cooldown_seconds=60 * 60,
        )
    )

    def pricing_precondition(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryDecision:
        market_date = _valid_market_date(incident.authority_identity)
        if market_date is None:
            return RecoveryDecision.block(
                "pricing_recovery_market_date_invalid",
                authority_identity=incident.authority_identity,
            )

        from backend.pricing_pipeline.health import expected_market_date

        expected = expected_market_date(context.now).isoformat()
        if market_date != expected:
            return RecoveryDecision.block(
                "pricing_recovery_not_current_expected_date",
                incident_market_date=market_date,
                expected_market_date=expected,
            )

        live = pricing_checker(
            context,
            client=resolved_client,
        )
        if live.outcome is CheckOutcome.HEALTHY:
            return RecoveryDecision.block(
                "pricing_failure_already_cleared",
                market_date=market_date,
            )
        if (
            live.failure_code != incident.failure_code
            or live.authority_identity != incident.authority_identity
        ):
            return RecoveryDecision.block(
                "pricing_failure_signature_changed",
                incident_failure=incident.failure_code,
                live_failure=live.failure_code,
                incident_authority=incident.authority_identity,
                live_authority=live.authority_identity,
            )

        batches = list(
            resolved_client.table("pokemon_scrape_batches")
            .select("id,market_date,status")
            .eq("market_date", market_date)
            .limit(1)
            .execute().data or []
        )
        batch = batches[0] if batches else None
        if not batch or str(batch.get("status") or "").lower() != "complete":
            return RecoveryDecision.block(
                "pricing_source_batch_not_complete",
                market_date=market_date,
                batch_id=batch and batch.get("id"),
                batch_status=batch and batch.get("status"),
            )
        return RecoveryDecision.allow(
            market_date=market_date,
            batch_id=batch.get("id"),
        )

    def pricing_execute(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryExecution:
        del context
        market_date = _valid_market_date(incident.authority_identity)
        if market_date is None:
            return RecoveryExecution.blocked(
                result={"status": "invalid_market_date"}
            )
        result = dict(pricing_runner(market_date) or {})
        returncode = int(result.get("returncode", 1))
        if returncode == 0:
            return RecoveryExecution.succeeded(
                result=result,
                mutation_performed=True,
            )
        if returncode in {3, 75}:
            return RecoveryExecution.blocked(result=result)
        return RecoveryExecution.failed(result=result)

    def pricing_verify(incident: IncidentRecord, context: RecoveryContext):
        del incident
        return pricing_checker(
            context,
            client=resolved_client,
        )

    registry.register(
        RecoveryRunbook(
            key=PRICING_RUNBOOK,
            version="1",
            check_key="pricing.multi_source.run_freshness",
            failure_code="DAILY_RUN_STALE_OR_INCOMPLETE",
            precondition=pricing_precondition,
            execute=pricing_execute,
            verify=pricing_verify,
            max_attempts=1,
            cooldown_seconds=2 * 60 * 60,
        )
    )

    def lease_precondition(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryDecision:
        live = lease_checker(_check_context(context), client=resolved_client)
        if live.outcome is CheckOutcome.HEALTHY:
            return RecoveryDecision.block(
                "scrape_lease_failure_already_cleared",
                authority_identity=incident.authority_identity,
            )
        if (
            live.failure_code != "scrape_job_lease_expired"
            or live.authority_identity != incident.authority_identity
        ):
            return RecoveryDecision.block(
                "scrape_lease_failure_signature_changed",
                incident_failure=incident.failure_code,
                live_failure=live.failure_code,
                incident_authority=incident.authority_identity,
                live_authority=live.authority_identity,
            )
        stale_jobs = list(live.evidence.get("stale_jobs") or [])
        if not stale_jobs:
            return RecoveryDecision.block(
                "scrape_lease_evidence_missing",
                stale_running_jobs=live.observed.get("stale_running_jobs"),
            )
        return RecoveryDecision.allow(
            market_date=context.now.astimezone(PHOENIX).date().isoformat(),
            stale_running_jobs=live.observed.get("stale_running_jobs"),
            stale_job_ids=[row.get("id") for row in stale_jobs[:20]],
        )

    def lease_execute(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryExecution:
        del incident, context
        reconciled = int(lease_reconciler() or 0)
        return RecoveryExecution.succeeded(
            result={"jobs_reconciled": reconciled},
            mutation_performed=reconciled > 0,
        )

    def lease_verify(incident: IncidentRecord, context: RecoveryContext):
        del incident
        return lease_checker(_check_context(context), client=resolved_client)

    registry.register(
        RecoveryRunbook(
            key=LEASE_RUNBOOK,
            version="1",
            check_key="scrape.queue_leases",
            failure_code="scrape_job_lease_expired",
            precondition=lease_precondition,
            execute=lease_execute,
            verify=lease_verify,
            max_attempts=1,
            cooldown_seconds=60 * 60,
        )
    )

    return registry
