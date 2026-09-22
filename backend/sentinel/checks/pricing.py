"""Sentinel adapter for the daily multi-source pricing-pipeline health module (P6M).

Reuses backend.pricing_pipeline.health.gather()/assess()/sentinel_results() as the sole
source of pricing-health logic. This module only wires those results into individually
addressable Sentinel checks and guarantees the underlying DB snapshot is gathered at most
once per Sentinel run, no matter how many pricing checks are registered/executed.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from backend.pricing_pipeline import health as pricing_health
from backend.sentinel.models import CheckResult
from backend.sentinel.registry import CheckContext

PRICING_CHECK_KEYS = (
    "pricing.multi_source.run_freshness",
    "pricing.multi_source.target_freshness",
    "pricing.ebay.budget_health",
    "pricing.ebay.quota_authority_v2",
    "pricing.ebay.evidence_freshness",
    "pricing.ebay.estimator_freshness",
    "pricing.multi_source.shadow_freshness",
    "pricing.canonical.source_guard",
    "pricing.multi_source.policy_drift",
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
        self._client = client
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
