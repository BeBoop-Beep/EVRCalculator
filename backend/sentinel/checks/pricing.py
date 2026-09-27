"""Sentinel adapter for the daily multi-source pricing-pipeline health module (P6M).

Reuses backend.pricing_pipeline.health.gather()/assess()/sentinel_results() as the sole
source of pricing-health logic. This module only wires those results into individually
addressable Sentinel checks and guarantees the underlying DB snapshot is gathered at most
once per Sentinel run, no matter how many pricing checks are registered/executed.
"""
from __future__ import annotations

import subprocess
from typing import Any, Callable, Dict, Optional

from backend.pricing_pipeline import health as pricing_health
from backend.sentinel.models import CheckResult, Severity
from backend.sentinel.registry import CheckContext

PRICING_CHECK_KEYS = (
    "pricing.multi_source.run_freshness",
    "pricing.ebay.calendar_continuity",
    "pricing.multi_source.target_freshness",
    "pricing.ebay.budget_health",
    "pricing.ebay.quota_authority_v2",
    "pricing.ebay.evidence_freshness",
    "pricing.ebay.estimator_freshness",
    "pricing.multi_source.shadow_freshness",
    "pricing.canonical.source_guard",
    "pricing.multi_source.policy_drift",
)


PRICING_SCHEDULER_CHECK_KEY = "pricing.ebay.scheduler"
PRICING_SCHEDULER_AUTHORITY = "multi-source-pricing-cron-v1"


def _default_client() -> Any:
    from backend.db.clients.supabase_client import create_service_role_client

    return create_service_role_client()


def check_pricing_scheduler(
    context: CheckContext,
    *,
    crontab_loader: Optional[Callable[[], str]] = None,
) -> CheckResult:
    """Verify the managed daily eBay pricing schedule exists on the runtime host."""
    if crontab_loader is None:
        def crontab_loader() -> str:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if result.returncode != 0:
                raise RuntimeError("crontab_unavailable")
            return result.stdout

    text = crontab_loader()
    begin = "# BEGIN multi-source-pricing (managed by install_multi_source_pricing_cron.sh)"
    end = "# END multi-source-pricing"
    in_block = False
    blocks = 0
    primary = 0
    retry = 0
    health = 0
    for raw in text.splitlines():
        line = raw.strip()
        if line == begin:
            blocks += 1
            in_block = True
            continue
        if line == end:
            in_block = False
            continue
        if not in_block or not line or line.startswith("#"):
            continue
        if "run_daily_multi_source_card_pricing" in line:
            if line.startswith("10 4 * * * "):
                primary += 1
            elif line.startswith("40 4,5,7-20 * * * "):
                retry += 1
        if "check_multi_source_pricing_health" in line:
            health += 1

    observed = {
        "managed_blocks": blocks,
        "primary_entries": primary,
        "retry_entries": retry,
        "health_entries": health,
    }
    if observed != {
        "managed_blocks": 1,
        "primary_entries": 1,
        "retry_entries": 1,
        "health_entries": 1,
    }:
        return CheckResult.failure(
            PRICING_SCHEDULER_CHECK_KEY,
            failure_code="EBAY_DAILY_SCHEDULE_MISSING",
            severity=Severity.WARNING,
            authority_identity=PRICING_SCHEDULER_AUTHORITY,
            observed=observed,
            checked_at=context.now,
        )
    return CheckResult.healthy(
        PRICING_SCHEDULER_CHECK_KEY,
        authority_identity=PRICING_SCHEDULER_AUTHORITY,
        observed=observed,
        checked_at=context.now,
    )


class PricingHealthSnapshot:
    """Lazily gathers pricing_pipeline.health state once, then serves every check from it.

    One instance must be shared across all pricing checks registered from the same
    build_*_registry() call. It is NOT a cross-run/global cache: a fresh instance is
    created every time the registry is built, so each Sentinel run re-gathers exactly once.
    """

    def __init__(
        self,
        *,
        client: Any,
        gather: Callable[..., Dict[str, Any]] = pricing_health.gather,
        sentinel_results: Callable[..., Any] = pricing_health.sentinel_results,
    ) -> None:
        self._client = client if client is not None else _default_client()
        self._gather = gather
        self._sentinel_results = sentinel_results
        self._results: Optional[Dict[str, CheckResult]] = None

    def _results_by_key(self, context: CheckContext) -> Dict[str, CheckResult]:
        if self._results is None:
            snapshot = self._gather(self._client, context.now)
            self._results = {
                result.check_key: result for result in self._sentinel_results(snapshot)
            }
        return self._results

    def get(self, key: str) -> Callable[[CheckContext], CheckResult]:
        def _run(context: CheckContext) -> CheckResult:
            return self._results_by_key(context)[key]

        return _run
