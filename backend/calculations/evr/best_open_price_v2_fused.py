"""V2-only fused Best-Open Price search.

This module deliberately leaves the validated V1 ``ExactBestOpenPriceSearch``
untouched.  It preserves the same exact-cent search domains and canonical
comparators, but scores a candidate price once and immediately compares that
same score against every still-active V2 authority (Overall RIP V12 and
Financial RIP V4).

The implementation is intentionally streaming: only one prepared physical
quantity is resident at a time.  This avoids both failure modes observed in the
Sep. 14 Phase-10 cohort run: a small score LRU caused the sequential Financial
pass to rescore millions of cents, while an unbounded quantity memo retained up
to 186 prepared distributions for one product.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from backend.calculations.evr.best_open_price import (
    BEST_OPEN_PRICE_METHOD_VERSION,
    BestOpenPriceSearchError,
    COMPARISON_AUTHORITY_FINANCIAL_V4,
    COMPARISON_AUTHORITY_OVERALL_V12,
    PreparedCanonicalCandidate,
    quantity_price_interval_cents,
)


@dataclass
class _AxisState:
    name: str
    authority: str
    current_rank: int
    benchmark: Mapping[str, Any]
    evaluations: int = 0
    comparator_seconds: float = 0.0
    scoring_seconds: float = 0.0
    lowest_price_cents: Optional[int] = None
    quantities: set[int] = field(default_factory=set)
    result: Optional[Dict[str, Any]] = None
    current_result: Optional[Dict[str, Any]] = None

    @property
    def is_leader(self) -> bool:
        return self.current_rank == 1


@dataclass
class DualBestOpenPriceSearch:
    """Exact V2 dual-threshold search with one scoring pass over shared prices.

    Search order is globally descending price, matching the proof obligation of
    ``ExactBestOpenPriceSearch`` without assuming comparator monotonicity:

    * Leader axes are valid on ``[current, budget]``.  Current market is first
      reconstructed as #1 (fail closed if it is not), then higher prices are
      inspected from budget down to current+1.  The first win is globally
      maximal; if none wins, current market is the exact threshold.
    * Non-leader axes are valid at or below current market.  Current is checked
      once; unresolved axes then inspect current-1 downward until the minimum
      positive-cent price whose allocation does not exceed
      ``max_quantity_to_construct``.  Again, the first win is globally maximal.

    At each inspected price the expensive candidate score is calculated once,
    then the unchanged ``PreparedCanonicalCandidate.compare`` authority logic
    is invoked for every active axis.  No cross-pass score cache is necessary.
    """

    product_id: str
    budget_cents: int
    current_price_cents: int
    current_quantity: int
    rip_current_rank: int
    rip_benchmark: Mapping[str, Any]
    financial_current_rank: int
    financial_benchmark: Mapping[str, Any]
    prepare_quantity: Callable[[int], PreparedCanonicalCandidate]
    source_authority_fingerprint: str
    expected_source_authority_fingerprint: str
    prepare_quantities: Optional[
        Callable[[Sequence[int]], Mapping[int, PreparedCanonicalCandidate]]
    ] = None
    max_quantity_to_construct: int = 4096

    # Retained as constructor-compatibility knobs for the prior V2 wrapper.
    # The fused implementation intentionally does not keep either cache.
    max_cached_quantities: int = 4
    quantity_batch_size: int = 8
    max_score_cache_entries: int = 4096

    _resident_quantity: Optional[int] = field(default=None, init=False)
    _resident_candidate: Optional[PreparedCanonicalCandidate] = field(default=None, init=False)
    _constructed_quantities: set[int] = field(default_factory=set, init=False)
    _quantity_construction_count: int = field(default=0, init=False)
    _max_resident_quantities: int = field(default=0, init=False)
    _batch_build_count: int = field(default=0, init=False)
    _batch_fallback_count: int = field(default=0, init=False)
    _score_count: int = field(default=0, init=False)
    _score_seconds: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if self.source_authority_fingerprint != self.expected_source_authority_fingerprint:
            raise BestOpenPriceSearchError("source-authority fingerprint mismatch")
        if min(self.budget_cents, self.current_price_cents, self.current_quantity) < 1:
            raise ValueError("budget, current price, and current quantity must be positive")
        if self.current_price_cents > self.budget_cents:
            raise ValueError("current market price exceeds the Full Market budget")
        if self.max_quantity_to_construct < 1:
            raise ValueError("max_quantity_to_construct must be positive")
        if self.quantity_batch_size < 1:
            raise ValueError("quantity_batch_size must be positive")

    def _validate_candidate(self, quantity: int, candidate: PreparedCanonicalCandidate) -> None:
        if candidate.product_id != self.product_id or candidate.quantity != quantity:
            raise BestOpenPriceSearchError("quantity candidate identity mismatch")

    def _build_candidate(self, quantity: int) -> PreparedCanonicalCandidate:
        """Build exactly one physical quantity, preferring the batch fast path.

        ``prepare_quantities([q])`` preserves the optimized independent-q
        construction used by the cohort runner without retaining the result
        after the scan moves to another quantity.  Any batch failure falls back
        to the correctness-first single-q factory, mirroring V1 behavior.
        """
        candidate: Optional[PreparedCanonicalCandidate] = None
        if self.prepare_quantities is not None:
            try:
                built = dict(self.prepare_quantities([quantity]))
                if set(built) != {quantity}:
                    raise BestOpenPriceSearchError(
                        "quantity batch returned the wrong quantity set"
                    )
                candidate = built[quantity]
                self._validate_candidate(quantity, candidate)
                self._batch_build_count += 1
            except Exception:
                self._batch_fallback_count += 1
                candidate = None
        if candidate is None:
            candidate = self.prepare_quantity(quantity)
            self._validate_candidate(quantity, candidate)

        self._constructed_quantities.add(quantity)
        self._quantity_construction_count += 1
        return candidate

    def _candidate(self, quantity: int) -> PreparedCanonicalCandidate:
        if self._resident_quantity == quantity and self._resident_candidate is not None:
            return self._resident_candidate
        self._resident_candidate = self._build_candidate(quantity)
        self._resident_quantity = quantity
        # The old candidate reference is replaced before this returns.  The
        # shared V2 layer therefore owns at most one prepared quantity.
        self._max_resident_quantities = max(self._max_resident_quantities, 1)
        return self._resident_candidate

    def _score(self, price_cents: int) -> tuple[PreparedCanonicalCandidate, Dict[str, Any]]:
        if not 1 <= price_cents <= self.budget_cents:
            raise ValueError("candidate price is outside the positive-cent Full Market domain")
        quantity = self.budget_cents // price_cents
        if quantity > self.max_quantity_to_construct:
            raise BestOpenPriceSearchError("candidate allocation exceeds max_quantity_to_construct")
        candidate = self._candidate(quantity)
        record = candidate.score_candidate(price_cents)
        self._score_count += 1
        self._score_seconds += float(record.get("scoringSeconds") or 0.0)
        return candidate, record

    def _compare(
        self,
        axis: _AxisState,
        candidate: PreparedCanonicalCandidate,
        score_record: Mapping[str, Any],
    ) -> Dict[str, Any]:
        wins = candidate.compare(score_record, axis.benchmark, authority=axis.authority)
        comparator_seconds = float(candidate._last_comparator_seconds or 0.0)
        axis.evaluations += 1
        axis.comparator_seconds += comparator_seconds
        axis.scoring_seconds += float(score_record.get("scoringSeconds") or 0.0)
        price_cents = int(score_record["priceCents"])
        quantity = int(score_record["quantity"])
        axis.lowest_price_cents = min(axis.lowest_price_cents or price_cents, price_cents)
        axis.quantities.add(quantity)
        return {
            **dict(score_record),
            "wins": bool(wins),
            "comparatorSeconds": comparator_seconds,
            "comparisonAuthority": axis.authority,
            # The score was produced by the fused stream rather than an LRU.
            # Reuse is reported at the dual-search diagnostics level.
            "scoreCacheHit": False,
        }

    def _axis_payload(
        self,
        axis: _AxisState,
        *,
        started: float,
    ) -> Dict[str, Any]:
        result = axis.result
        if result is None:
            return {
                "methodVersion": BEST_OPEN_PRICE_METHOD_VERSION,
                "status": "unresolved_extreme_quantity",
                "productId": self.product_id,
                "currentRank": axis.current_rank,
                "currentPriceCents": self.current_price_cents,
                "threshold": None,
                "benchmarkProductId": axis.benchmark.get("sealedProductId"),
                "benchmarkOverallRipV12Score": axis.benchmark.get("overallRipV12Score"),
                "evaluationCount": axis.evaluations,
                "physicalQuantitiesConstructed": sorted(axis.quantities),
                "quantityCacheHits": 0,
                "quantityCacheMisses": len(axis.quantities),
                "quantityCacheEvictions": 0,
                "maximumResidentQuantities": 1 if axis.evaluations else 0,
                "bracketExpansions": 0,
                "bracketRefinements": 0,
                "monotonicityFallbackCount": 0,
                "minimumQuantityInspected": min(axis.quantities) if axis.quantities else None,
                "maximumQuantityInspected": max(axis.quantities) if axis.quantities else None,
                "lowestCandidatePriceCents": axis.lowest_price_cents,
                "candidateScoringSeconds": axis.scoring_seconds,
                "comparatorSeconds": axis.comparator_seconds,
                "exactnessVerificationSeconds": 0.0,
                "quantityBatchBuilds": self._batch_build_count,
                "quantityBatchQuantities": self._batch_build_count,
                "quantityBatchFallbacks": self._batch_fallback_count,
                "maximumPendingBatchCandidates": 1 if self._batch_build_count else 0,
                "wallSeconds": time.perf_counter() - started,
            }

        if not result.get("wins"):
            raise BestOpenPriceSearchError("returned threshold does not win")
        price_cents = int(result["priceCents"])
        next_price = price_cents + 1 if price_cents < self.budget_cents else None
        next_wins: Optional[bool] = None
        if next_price is not None and (axis.is_leader or next_price <= self.current_price_cents):
            # Every legal price above the first winning cent was already
            # inspected in descending order, so P*+1 is proven losing without
            # rescoring it here.
            next_wins = False
        low, high = quantity_price_interval_cents(
            self.budget_cents, int(result["quantity"])
        )
        exactness = {
            "thresholdWins": True,
            "nextPriceCents": next_price,
            "nextPriceWins": next_wins,
            "oneCentMaximal": next_wins is not True,
            "quantityIntervalLowCents": low,
            "quantityIntervalHighCents": high,
            "nextCentCrossesQuantityBoundary": (
                next_price is not None
                and self.budget_cents // next_price != int(result["quantity"])
            ),
        }
        return {
            "methodVersion": BEST_OPEN_PRICE_METHOD_VERSION,
            "status": "exact",
            "productId": self.product_id,
            "currentRank": axis.current_rank,
            "currentPriceCents": self.current_price_cents,
            "threshold": dict(result),
            "benchmarkProductId": axis.benchmark.get("sealedProductId"),
            "benchmarkOverallRipV12Score": axis.benchmark.get("overallRipV12Score"),
            "evaluationCount": axis.evaluations,
            "physicalQuantitiesConstructed": sorted(axis.quantities),
            "quantityCacheHits": 0,
            "quantityCacheMisses": len(axis.quantities),
            "quantityCacheEvictions": 0,
            "maximumResidentQuantities": 1,
            "bracketExpansions": 0,
            "bracketRefinements": 0,
            "monotonicityFallbackCount": 0,
            "minimumQuantityInspected": min(axis.quantities) if axis.quantities else None,
            "maximumQuantityInspected": max(axis.quantities) if axis.quantities else None,
            "lowestCandidatePriceCents": axis.lowest_price_cents,
            "candidateScoringSeconds": axis.scoring_seconds,
            "comparatorSeconds": axis.comparator_seconds,
            "exactnessVerificationSeconds": 0.0,
            "quantityBatchBuilds": self._batch_build_count,
            "quantityBatchQuantities": self._batch_build_count,
            "quantityBatchFallbacks": self._batch_fallback_count,
            "maximumPendingBatchCandidates": 1 if self._batch_build_count else 0,
            "wallSeconds": time.perf_counter() - started,
            "exactness": exactness,
        }

    def search(self) -> Dict[str, Any]:
        started = time.perf_counter()
        rip = _AxisState(
            "rip",
            COMPARISON_AUTHORITY_OVERALL_V12,
            self.rip_current_rank,
            self.rip_benchmark,
        )
        financial = _AxisState(
            "financial",
            COMPARISON_AUTHORITY_FINANCIAL_V4,
            self.financial_current_rank,
            self.financial_benchmark,
        )
        axes = (rip, financial)

        q0 = self.budget_cents // self.current_price_cents
        if q0 > self.max_quantity_to_construct:
            rip_result = self._axis_payload(rip, started=started)
            financial_result = self._axis_payload(financial, started=started)
            return {
                "ripResult": rip_result,
                "financialResult": financial_result,
                "diagnostics": self._diagnostics(rip, financial),
            }

        # Current market is the only price shared by leader and non-leader
        # domains. Score it once. Leaders must reconstruct as #1; non-leaders
        # that already win resolve at market immediately.
        current_candidate, current_score = self._score(self.current_price_cents)
        for axis in axes:
            evaluated = self._compare(axis, current_candidate, current_score)
            axis.current_result = evaluated
            if axis.is_leader:
                if not evaluated["wins"]:
                    raise BestOpenPriceSearchError(
                        f"published current {axis.name} leader does not reconstruct as #1"
                    )
            elif evaluated["wins"]:
                axis.result = evaluated

        # Leader domain: globally descending from the budget ceiling. A first
        # win is the exact maximum for that axis. Axes resolve independently.
        high_active = [axis for axis in axes if axis.is_leader]
        for price_cents in range(self.budget_cents, self.current_price_cents, -1):
            unresolved = [axis for axis in high_active if axis.result is None]
            if not unresolved:
                break
            candidate, score = self._score(price_cents)
            for axis in unresolved:
                evaluated = self._compare(axis, candidate, score)
                if evaluated["wins"]:
                    axis.result = evaluated

        # A leader with no higher-price win remains #1 exactly through current.
        for axis in high_active:
            if axis.result is None:
                axis.result = axis.current_result

        # Non-leader domain: inspect lower prices globally descending. The
        # lower bound is the first cent whose floor allocation is <= max_q.
        max_q = min(self.budget_cents, self.max_quantity_to_construct)
        minimum_price_cents = self.budget_cents // (max_q + 1) + 1
        low_active = [axis for axis in axes if not axis.is_leader and axis.result is None]
        for price_cents in range(self.current_price_cents - 1, minimum_price_cents - 1, -1):
            unresolved = [axis for axis in low_active if axis.result is None]
            if not unresolved:
                break
            candidate, score = self._score(price_cents)
            for axis in unresolved:
                evaluated = self._compare(axis, candidate, score)
                if evaluated["wins"]:
                    axis.result = evaluated

        rip_result = self._axis_payload(rip, started=started)
        financial_result = self._axis_payload(financial, started=started)
        return {
            "ripResult": rip_result,
            "financialResult": financial_result,
            "diagnostics": self._diagnostics(rip, financial),
        }

    def _diagnostics(self, rip: _AxisState, financial: _AxisState) -> Dict[str, Any]:
        naive_score_count = rip.evaluations + financial.evaluations
        reuse_savings = naive_score_count - self._score_count
        total_cache_events = reuse_savings + self._score_count
        return {
            "uniqueCandidatePricesScored": self._score_count,
            "sharedScoreCacheHits": reuse_savings,
            "scoreCacheHits": reuse_savings,
            "scoreCacheMisses": self._score_count,
            "scoreCacheEvictions": 0,
            "scoreCacheHitRate": (
                reuse_savings / total_cache_events if total_cache_events else None
            ),
            "financialComparatorEvaluations": financial.evaluations,
            "ripComparatorEvaluations": rip.evaluations,
            "uniqueQuantitiesConstructed": len(self._constructed_quantities),
            "quantityConstructionCount": self._quantity_construction_count,
            "maximumResidentSharedQuantities": self._max_resident_quantities,
            "naiveScoreCount": naive_score_count,
            "scoreReuseSavings": reuse_savings,
            "sharedCandidateScoringSeconds": self._score_seconds,
            "quantityBatchBuilds": self._batch_build_count,
            "quantityBatchFallbacks": self._batch_fallback_count,
            "fusedStreaming": True,
        }
