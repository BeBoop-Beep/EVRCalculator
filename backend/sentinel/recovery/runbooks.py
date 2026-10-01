"""Initial allowlisted recovery runbooks for inDex Sentinel P6.

The allowlist contains only bounded, idempotent repairs that invoke existing
canonical entrypoints:
1. market.freshness / market_publication_stale
2. market.freshness / market_snapshot_date_divergence
3. scrape.queue_leases / scrape_job_lease_expired
4. pricing.multi_source.run_freshness / DAILY_RUN_STALE_OR_INCOMPLETE
5. pricing.ebay.scheduler / EBAY_DAILY_SCHEDULE_MISSING
6. market_explorer.maintenance_scheduler / MARKET_EXPLORER_MAINTENANCE_SCHEDULE_MISSING
7. market_explorer.maintenance_progress / MARKET_EXPLORER_CONVERGENCE_STALLED
8. sentinel.runtime_scheduler / SENTINEL_RUNTIME_SCHEDULE_MISSING

Historical eBay continuity gaps remain observation-only because current active
listings cannot truthfully reconstruct a missed past market date.
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
from backend.sentinel.checks.pricing import (
    PRICING_SCHEDULER_CHECK_KEY,
    check_pricing_scheduler,
)
from backend.sentinel.checks.runtime_scheduler import (
    SENTINEL_SCHEDULER_CHECK_KEY,
    check_sentinel_scheduler,
)
from backend.sentinel.checks.explorer import (
    MARKET_EXPLORER_PROGRESS_CHECK_KEY,
    MARKET_EXPLORER_SCHEDULER_CHECK_KEY,
    check_market_explorer_progress,
    check_market_explorer_scheduler,
)
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
PUBLICATION_DIVERGENCE_RUNBOOK = "publish_divergent_market_surfaces_v1"
LEASE_RUNBOOK = "reconcile_stale_scrape_leases_v1"
PRICING_RUNBOOK = "run_daily_multi_source_pricing_v1"
PRICING_SCHEDULER_RUNBOOK = "install_multi_source_pricing_cron_v1"
MARKET_EXPLORER_SCHEDULER_RUNBOOK = "install_market_explorer_prewarm_cron_v1"
MARKET_EXPLORER_PROGRESS_RUNBOOK = "advance_market_explorer_convergence_v1"
SENTINEL_SCHEDULER_RUNBOOK = "install_sentinel_runtime_cron_v1"

REPO_ROOT = Path(__file__).resolve().parents[3]
PRICING_LOCK_PATH = "/tmp/multi-source-pricing.lock"
PRICING_STATE_DIR = "/home/ubuntu/state/multi_source_pricing"
PRICING_CRON_INSTALLER = REPO_ROOT / "infra" / "oracle" / "install_multi_source_pricing_cron.sh"
MARKET_EXPLORER_CRON_INSTALLER = (
    REPO_ROOT / "infra" / "oracle" / "install_market_explorer_prewarm_cron.sh"
)
MARKET_EXPLORER_GUARDED_WORKER = (
    REPO_ROOT / "infra" / "oracle" / "run_market_explorer_prewarm_guarded.sh"
)
SENTINEL_CRON_INSTALLER = REPO_ROOT / "infra" / "oracle" / "install_sentinel_cron.sh"


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


def build_safe_recovery_registry(
    *,
    client: Any = None,
    publish_if_needed_fn: Optional[Callable[..., dict]] = None,
    gate_evaluator: Optional[Callable[..., Any]] = None,
    market_freshness_checker: Optional[Callable[..., Any]] = None,
    lease_reconciler: Optional[Callable[[], int]] = None,
    lease_checker: Optional[Callable[..., Any]] = None,
    pricing_run_fn: Optional[Callable[[str], dict]] = None,
    pricing_health_checker: Optional[Callable[..., Any]] = None,
    pricing_scheduler_checker: Optional[Callable[..., Any]] = None,
    pricing_cron_installer: Optional[Callable[[], dict]] = None,
    market_explorer_scheduler_checker: Optional[Callable[..., Any]] = None,
    market_explorer_cron_installer: Optional[Callable[[], dict]] = None,
    market_explorer_progress_checker: Optional[Callable[..., Any]] = None,
    market_explorer_worker: Optional[Callable[[], dict]] = None,
    sentinel_scheduler_checker: Optional[Callable[..., Any]] = None,
    sentinel_cron_installer: Optional[Callable[[], dict]] = None,
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

    if pricing_health_checker is None:
        from backend.pricing_pipeline import health as pricing_health

        def pricing_health_checker(context: CheckContext, *, client: Any, check_key: str):
            snapshot = pricing_health.gather(client, context.now)
            results = {
                result.check_key: result
                for result in pricing_health.sentinel_results(snapshot)
            }
            return results[check_key]

    if pricing_scheduler_checker is None:
        pricing_scheduler_checker = check_pricing_scheduler

    if pricing_run_fn is None:
        def pricing_run_fn(market_date: str) -> dict:
            env = os.environ.copy()
            env["EVR_PRICING_STATE_DIR"] = env.get(
                "EVR_PRICING_STATE_DIR", PRICING_STATE_DIR
            )
            args = [
                "/usr/bin/flock",
                "-n",
                "--conflict-exit-code",
                "99",
                PRICING_LOCK_PATH,
                sys.executable,
                "-m",
                "backend.scripts.run_daily_multi_source_card_pricing",
                "--json",
                "--resume",
                "--no-frontend-env-fallback",
                "--market-date",
                market_date,
            ]
            result = subprocess.run(
                args,
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=60 * 60,
            )
            status = (
                "complete" if result.returncode == 0
                else "already_running" if result.returncode in {3, 99}
                else "waiting_for_batch" if result.returncode == 75
                else "failed"
            )
            return {"status": status, "exit_code": int(result.returncode)}

    if pricing_cron_installer is None:
        def pricing_cron_installer() -> dict:
            result = subprocess.run(
                ["bash", str(PRICING_CRON_INSTALLER), "--apply"],
                cwd=str(REPO_ROOT),
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                check=False,
                timeout=15 * 60,
            )
            return {
                "status": "installed" if result.returncode == 0 else "failed",
                "exit_code": int(result.returncode),
            }

    if market_explorer_scheduler_checker is None:
        market_explorer_scheduler_checker = check_market_explorer_scheduler
    if sentinel_scheduler_checker is None:
        sentinel_scheduler_checker = check_sentinel_scheduler
    if market_explorer_progress_checker is None:
        market_explorer_progress_checker = check_market_explorer_progress

    if market_explorer_cron_installer is None:
        def market_explorer_cron_installer() -> dict:
            result = subprocess.run(
                ["bash", str(MARKET_EXPLORER_CRON_INSTALLER), "--apply"],
                cwd=str(REPO_ROOT),
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                check=False,
                timeout=15 * 60,
            )
            return {
                "status": "installed" if result.returncode == 0 else "failed",
                "exit_code": int(result.returncode),
            }

    if market_explorer_worker is None:
        def market_explorer_worker() -> dict:
            result = subprocess.run(
                ["bash", str(MARKET_EXPLORER_GUARDED_WORKER)],
                cwd=str(REPO_ROOT),
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                check=False,
                timeout=15 * 60,
            )
            status = (
                "advanced" if result.returncode == 0
                else "deferred" if result.returncode in {3, 4, 75}
                else "failed"
            )
            return {"status": status, "exit_code": int(result.returncode)}

    if sentinel_cron_installer is None:
        def sentinel_cron_installer() -> dict:
            result = subprocess.run(
                ["bash", str(SENTINEL_CRON_INSTALLER), "--apply"],
                cwd=str(REPO_ROOT),
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                check=False,
                timeout=15 * 60,
            )
            return {
                "status": "installed" if result.returncode == 0 else "failed",
                "exit_code": int(result.returncode),
            }

    registry = RecoveryRegistry()

    def _publication_precondition(
        incident: IncidentRecord,
        context: RecoveryContext,
        *,
        expected_failure_code: str,
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
            live.failure_code != expected_failure_code
            or live.authority_identity != incident.authority_identity
        ):
            return RecoveryDecision.block(
                "publication_failure_signature_changed",
                incident_failure=incident.failure_code,
                live_failure=live.failure_code,
                incident_authority=incident.authority_identity,
                live_authority=live.authority_identity,
            )

        if expected_failure_code == "market_snapshot_date_divergence":
            dates = dict(live.observed.get("authority_dates") or {})
            lagging = sorted(
                key for key, value in dates.items()
                if value and str(value)[:10] != market_date
            )
            missing = sorted(key for key, value in dates.items() if not value)
            divergent = sorted(set(lagging + missing))
            if divergent and set(divergent).issubset({"explorer_v2"}):
                return RecoveryDecision.block(
                    "explorer_convergence_owned_by_maintained_worker",
                    market_date=market_date,
                    divergent_authorities=divergent,
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

    def publication_precondition(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryDecision:
        return _publication_precondition(
            incident,
            context,
            expected_failure_code="market_publication_stale",
        )

    def publication_divergence_precondition(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryDecision:
        return _publication_precondition(
            incident,
            context,
            expected_failure_code="market_snapshot_date_divergence",
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
            "deferred_database_safety_hold",
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
            precondition=publication_divergence_precondition,
            execute=publication_execute,
            verify=publication_verify,
            max_attempts=1,
            cooldown_seconds=60 * 60,
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

    def pricing_run_precondition(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryDecision:
        market_date = _valid_market_date(incident.authority_identity)
        if market_date is None:
            return RecoveryDecision.block(
                "pricing_recovery_market_date_invalid",
                authority_identity=incident.authority_identity,
            )
        live = pricing_health_checker(
            _check_context(context),
            client=resolved_client,
            check_key="pricing.multi_source.run_freshness",
        )
        if live.outcome is CheckOutcome.HEALTHY:
            return RecoveryDecision.block(
                "pricing_failure_already_cleared", market_date=market_date
            )
        if (
            live.failure_code != "DAILY_RUN_STALE_OR_INCOMPLETE"
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
            .select("id,status,promoted_at,missing_set_count")
            .eq("market_date", market_date)
            .order("id", desc=True)
            .limit(1)
            .execute().data or []
        )
        batch = batches[0] if batches else None
        if (
            not batch
            or str(batch.get("status") or "") != "complete"
            or not batch.get("promoted_at")
            or int(batch.get("missing_set_count") or 0) != 0
        ):
            return RecoveryDecision.block(
                "pricing_source_batch_not_complete",
                market_date=market_date,
                batch_id=(batch or {}).get("id"),
                batch_status=(batch or {}).get("status"),
                missing_set_count=(batch or {}).get("missing_set_count"),
            )
        return RecoveryDecision.allow(
            market_date=market_date,
            batch_id=batch.get("id"),
        )

    def pricing_run_execute(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryExecution:
        del context
        market_date = _valid_market_date(incident.authority_identity)
        if market_date is None:
            return RecoveryExecution.blocked(result={"status": "invalid_market_date"})
        result = dict(pricing_run_fn(market_date) or {})
        status = str(result.get("status") or "")
        if status == "complete":
            return RecoveryExecution.succeeded(result=result, mutation_performed=True)
        if status in {"already_running", "waiting_for_batch"}:
            return RecoveryExecution.blocked(result=result)
        return RecoveryExecution.failed(result=result)

    def pricing_run_verify(incident: IncidentRecord, context: RecoveryContext):
        del incident
        return pricing_health_checker(
            _check_context(context),
            client=resolved_client,
            check_key="pricing.multi_source.run_freshness",
        )

    registry.register(
        RecoveryRunbook(
            key=PRICING_RUNBOOK,
            version="1",
            check_key="pricing.multi_source.run_freshness",
            failure_code="DAILY_RUN_STALE_OR_INCOMPLETE",
            precondition=pricing_run_precondition,
            execute=pricing_run_execute,
            verify=pricing_run_verify,
            max_attempts=1,
            cooldown_seconds=60 * 60,
        )
    )

    def pricing_scheduler_precondition(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryDecision:
        live = pricing_scheduler_checker(_check_context(context))
        if live.outcome is CheckOutcome.HEALTHY:
            return RecoveryDecision.block("pricing_scheduler_already_healthy")
        if live.failure_code != "EBAY_DAILY_SCHEDULE_MISSING":
            return RecoveryDecision.block(
                "pricing_scheduler_failure_signature_changed",
                live_failure=live.failure_code,
            )
        return RecoveryDecision.allow(observed=dict(live.observed))

    def pricing_scheduler_execute(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryExecution:
        del incident, context
        result = dict(pricing_cron_installer() or {})
        if str(result.get("status") or "") == "installed":
            return RecoveryExecution.succeeded(result=result, mutation_performed=True)
        return RecoveryExecution.failed(result=result)

    def pricing_scheduler_verify(incident: IncidentRecord, context: RecoveryContext):
        del incident
        return pricing_scheduler_checker(_check_context(context))

    registry.register(
        RecoveryRunbook(
            key=PRICING_SCHEDULER_RUNBOOK,
            version="1",
            check_key=PRICING_SCHEDULER_CHECK_KEY,
            failure_code="EBAY_DAILY_SCHEDULE_MISSING",
            precondition=pricing_scheduler_precondition,
            execute=pricing_scheduler_execute,
            verify=pricing_scheduler_verify,
            max_attempts=1,
            cooldown_seconds=60 * 60,
        )
    )

    def market_explorer_scheduler_precondition(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryDecision:
        live = market_explorer_scheduler_checker(_check_context(context))
        if live.outcome is CheckOutcome.HEALTHY:
            return RecoveryDecision.block("market_explorer_scheduler_already_healthy")
        if live.failure_code != "MARKET_EXPLORER_MAINTENANCE_SCHEDULE_MISSING":
            return RecoveryDecision.block(
                "market_explorer_scheduler_failure_signature_changed",
                live_failure=live.failure_code,
            )
        return RecoveryDecision.allow(observed=dict(live.observed))

    def market_explorer_scheduler_execute(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryExecution:
        del incident, context
        result = dict(market_explorer_cron_installer() or {})
        if str(result.get("status") or "") == "installed":
            return RecoveryExecution.succeeded(result=result, mutation_performed=True)
        return RecoveryExecution.failed(result=result)

    def market_explorer_scheduler_verify(
        incident: IncidentRecord, context: RecoveryContext
    ):
        del incident
        return market_explorer_scheduler_checker(_check_context(context))

    registry.register(
        RecoveryRunbook(
            key=MARKET_EXPLORER_SCHEDULER_RUNBOOK,
            version="1",
            check_key=MARKET_EXPLORER_SCHEDULER_CHECK_KEY,
            failure_code="MARKET_EXPLORER_MAINTENANCE_SCHEDULE_MISSING",
            precondition=market_explorer_scheduler_precondition,
            execute=market_explorer_scheduler_execute,
            verify=market_explorer_scheduler_verify,
            max_attempts=1,
            cooldown_seconds=60 * 60,
        )
    )

    def market_explorer_progress_precondition(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryDecision:
        live = market_explorer_progress_checker(
            _check_context(context), client=resolved_client
        )
        if live.outcome is CheckOutcome.HEALTHY:
            return RecoveryDecision.block(
                "market_explorer_convergence_already_progressing",
                authority_identity=incident.authority_identity,
            )
        if live.failure_code != "MARKET_EXPLORER_CONVERGENCE_STALLED":
            return RecoveryDecision.block(
                "market_explorer_progress_failure_signature_changed",
                live_failure=live.failure_code,
            )
        if (
            incident.authority_identity
            and live.authority_identity != incident.authority_identity
        ):
            return RecoveryDecision.block(
                "market_explorer_progress_authority_changed",
                incident_authority=incident.authority_identity,
                live_authority=live.authority_identity,
            )
        return RecoveryDecision.allow(
            authority_identity=live.authority_identity,
            observed=dict(live.observed),
        )

    def market_explorer_progress_execute(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryExecution:
        del incident, context
        result = dict(market_explorer_worker() or {})
        status = str(result.get("status") or "")
        if status == "advanced":
            return RecoveryExecution.succeeded(result=result, mutation_performed=True)
        if status == "deferred":
            return RecoveryExecution.blocked(result=result)
        return RecoveryExecution.failed(result=result)

    def market_explorer_progress_verify(
        incident: IncidentRecord, context: RecoveryContext
    ):
        del incident
        return market_explorer_progress_checker(
            _check_context(context), client=resolved_client
        )

    registry.register(
        RecoveryRunbook(
            key=MARKET_EXPLORER_PROGRESS_RUNBOOK,
            version="1",
            check_key=MARKET_EXPLORER_PROGRESS_CHECK_KEY,
            failure_code="MARKET_EXPLORER_CONVERGENCE_STALLED",
            precondition=market_explorer_progress_precondition,
            execute=market_explorer_progress_execute,
            verify=market_explorer_progress_verify,
            max_attempts=1,
            cooldown_seconds=30 * 60,
        )
    )

    def sentinel_scheduler_precondition(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryDecision:
        live = sentinel_scheduler_checker(_check_context(context))
        if live.outcome is CheckOutcome.HEALTHY:
            return RecoveryDecision.block("sentinel_scheduler_already_healthy")
        if live.failure_code != "SENTINEL_RUNTIME_SCHEDULE_MISSING":
            return RecoveryDecision.block(
                "sentinel_scheduler_failure_signature_changed",
                live_failure=live.failure_code,
            )
        return RecoveryDecision.allow(observed=dict(live.observed))

    def sentinel_scheduler_execute(
        incident: IncidentRecord, context: RecoveryContext
    ) -> RecoveryExecution:
        del incident, context
        result = dict(sentinel_cron_installer() or {})
        if str(result.get("status") or "") == "installed":
            return RecoveryExecution.succeeded(result=result, mutation_performed=True)
        return RecoveryExecution.failed(result=result)

    def sentinel_scheduler_verify(
        incident: IncidentRecord, context: RecoveryContext
    ):
        del incident
        return sentinel_scheduler_checker(_check_context(context))

    registry.register(
        RecoveryRunbook(
            key=SENTINEL_SCHEDULER_RUNBOOK,
            version="1",
            check_key=SENTINEL_SCHEDULER_CHECK_KEY,
            failure_code="SENTINEL_RUNTIME_SCHEDULE_MISSING",
            precondition=sentinel_scheduler_precondition,
            execute=sentinel_scheduler_execute,
            verify=sentinel_scheduler_verify,
            max_attempts=1,
            cooldown_seconds=60 * 60,
        )
    )

    return registry
