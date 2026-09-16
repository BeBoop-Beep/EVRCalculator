"""Internal exact-cent Best-Open Price search infrastructure (no persistence)."""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from backend.calculations.evr.budget_normalized_product_ranking import (
    SORT_AUTHORITY_V12,
    rank_budget_cohort,
    rank_by_financial_only,
)
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.financial_rip_v4 import project_financial_rip_v4_from_v3_payload
from backend.desirability.weighted_rip import compute_overall_rip_v12

BEST_OPEN_PRICE_METHOD_VERSION = "budget_product_best_open_price_full_market_v1"
BEST_OPEN_PRICE_V2_METHOD_VERSION = "budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12"

COMPARISON_AUTHORITY_OVERALL_V12 = "overall_v12"
COMPARISON_AUTHORITY_FINANCIAL_V4 = "financial_v4"


class BestOpenPriceSearchError(RuntimeError):
    pass


def quantity_price_interval_cents(budget_cents: int, quantity: int) -> tuple[int, int]:
    if budget_cents < 1 or quantity < 1:
        raise ValueError("budget_cents and quantity must be positive")
    return budget_cents // (quantity + 1) + 1, budget_cents // quantity


@dataclass
class PreparedCanonicalCandidate:
    product_id: str
    quantity: int
    distribution: PreparedFinancialRipDistribution
    collector_appeal_score: float
    chase_accessibility_raw: float
    target_budget: float
    min_simulation_count: int = 0
    _last_comparator_seconds: float = field(default=0.0, init=False)

    def score_candidate(self, price_cents: int) -> Dict[str, Any]:
        """Pure candidate-price scoring. No comparison, no winner determination."""
        score_started = time.perf_counter()
        # Mirror whole_unit_allocation() exactly. The canonical Budget Ranking
        # first converts the cent price to a float dollar price and THEN
        # multiplies by quantity. Reordering these IEEE-754 operations
        # (quantity * cents / 100) can change the stored float by ~1e-13 and,
        # at a Financial RIP rounding boundary, change the published score.
        unit_price = price_cents / 100.0
        capital = self.quantity * unit_price
        kwargs = {} if not self.min_simulation_count else {"min_simulation_count": self.min_simulation_count}
        v3 = self.distribution.score(capital, **kwargs)
        v4 = project_financial_rip_v4_from_v3_payload(v3)
        v12 = compute_overall_rip_v12(
            v4.get("score"), self.chase_accessibility_raw, self.collector_appeal_score
        )
        raw = {key: record.get("raw") for key, record in
               ((v3.get("audit") or {}).get("normalizedInputs") or {}).items()}
        scoring_seconds = time.perf_counter() - score_started
        return {
            "sealedProductId": self.product_id,
            "priceCents": price_cents,
            "quantity": self.quantity,
            "targetBudget": self.target_budget,
            "actualCommittedCapital": capital,
            "financialRipV3Score": v3.get("score"),
            "financialRipV4Score": v4.get("score"),
            "overallRipV12Score": v12.get("score"),
            "overallRipV12Rankable": bool(v12.get("rankable")),
            "chanceToRecoverCapital": raw.get("true_win_probability"),
            "scoringSeconds": scoring_seconds,
        }

    def compare(self, score_record: Mapping[str, Any], benchmark: Mapping[str, Any], *,
                authority: str = COMPARISON_AUTHORITY_OVERALL_V12) -> bool:
        """Winner determination only. Never rescoring -- score_record is already computed."""
        comparator_started = time.perf_counter()
        if authority == COMPARISON_AUTHORITY_OVERALL_V12:
            ranked = rank_budget_cohort([score_record, dict(benchmark)], sort_authority=SORT_AUTHORITY_V12)
            wins = bool(ranked and ranked[0]["sealedProductId"] == self.product_id)
        elif authority == COMPARISON_AUTHORITY_FINANCIAL_V4:
            # Guard: rank_by_financial_only() deliberately applies no
            # rankability filter (callers control cohort membership), but a
            # pairwise candidate-vs-benchmark winner check must never report
            # a win for a candidate with no Financial RIP V4 evidence of its
            # own -- otherwise, when BOTH sides are unscored, the sort falls
            # through financial_only_comparator_key()'s -inf fallback entirely
            # to the sealedProductId string tie-break and a candidate can
            # "win" purely by alphabetical accident.
            if score_record.get("financialRipV4Score") is None:
                wins = False
            else:
                ranked = rank_by_financial_only([score_record, dict(benchmark)])
                wins = bool(ranked and ranked[0]["sealedProductId"] == self.product_id)
        else:
            raise ValueError(f"unknown comparison authority {authority!r}")
        self._last_comparator_seconds = time.perf_counter() - comparator_started
        return wins

    def evaluate(self, price_cents: int, benchmark: Mapping[str, Any], *,
                 comparison_authority: str = COMPARISON_AUTHORITY_OVERALL_V12) -> Dict[str, Any]:
        score_record = self.score_candidate(price_cents)
        wins = self.compare(score_record, benchmark, authority=comparison_authority)
        comparator_seconds = self._last_comparator_seconds
        return {
            "wins": wins,
            "priceCents": score_record["priceCents"],
            "quantity": score_record["quantity"],
            "financialRipV3Score": score_record["financialRipV3Score"],
            "financialRipV4Score": score_record["financialRipV4Score"],
            "overallRipV12Score": score_record["overallRipV12Score"],
            "chanceToRecoverCapital": score_record["chanceToRecoverCapital"],
            "actualCommittedCapital": score_record["actualCommittedCapital"],
            "scoringSeconds": score_record["scoringSeconds"],
            "comparatorSeconds": comparator_seconds,
            "comparisonAuthority": comparison_authority,
        }


@dataclass
class SharedScoreCache:
    """Scores a (quantity, price_cents) candidate once, serves every
    comparison authority against it from the same score record.

    The Financial RIP V3 Monte Carlo simulation inside
    PreparedCanonicalCandidate.score_candidate() is the expensive step; the
    comparator dispatch inside .compare() is cheap. A dual-threshold engine
    (RIP + FINANCIAL_V4 searches over the same product) shares this cache so
    neither search rescoring a price the other already scored.
    """
    max_entries: int = 4096
    _scores: "OrderedDict[tuple[int, int], Dict[str, Any]]" = field(default_factory=OrderedDict, init=False)
    hits: int = field(default=0, init=False)
    misses: int = field(default=0, init=False)
    financial_comparator_evaluations: int = field(default=0, init=False)
    rip_comparator_evaluations: int = field(default=0, init=False)
    evictions: int = field(default=0, init=False)

    def get_or_score(self, candidate: "PreparedCanonicalCandidate", price_cents: int) -> tuple[Dict[str, Any], bool]:
        """Returns (score_record, was_hit). ``score_record`` is a shallow copy
        of the live cached entry -- a caller mutating it can never corrupt the
        cache for the other comparison authority sharing this record."""
        key = (candidate.quantity, price_cents)
        if key in self._scores:
            self.hits += 1
            self._scores.move_to_end(key)
            return dict(self._scores[key]), True
        self.misses += 1
        record = candidate.score_candidate(price_cents)
        self._scores[key] = record
        while len(self._scores) > self.max_entries:
            self._scores.popitem(last=False)
            self.evictions += 1
        return dict(record), False

    def evaluate(self, candidate: "PreparedCanonicalCandidate", price_cents: int,
                 benchmark: Mapping[str, Any], *, authority: str) -> Dict[str, Any]:
        if authority == COMPARISON_AUTHORITY_FINANCIAL_V4:
            self.financial_comparator_evaluations += 1
        elif authority == COMPARISON_AUTHORITY_OVERALL_V12:
            self.rip_comparator_evaluations += 1
        else:
            raise ValueError(f"unknown comparison authority {authority!r}")
        score_record, was_hit = self.get_or_score(candidate, price_cents)
        wins = candidate.compare(score_record, benchmark, authority=authority)
        return {
            **score_record,
            "wins": wins,
            "comparatorSeconds": candidate._last_comparator_seconds,
            "comparisonAuthority": authority,
            "scoreCacheHit": was_hit,
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "uniqueCandidatePricesScored": self.misses,
            "sharedScoreCacheHits": self.hits,
            "scoreCacheHits": self.hits,
            "scoreCacheMisses": self.misses,
            "scoreCacheEvictions": self.evictions,
            "financialComparatorEvaluations": self.financial_comparator_evaluations,
            "ripComparatorEvaluations": self.rip_comparator_evaluations,
        }


@dataclass
class ExactBestOpenPriceSearch:
    product_id: str
    budget_cents: int
    current_price_cents: int
    current_quantity: int
    current_rank: int
    benchmark: Mapping[str, Any]
    prepare_quantity: Callable[[int], PreparedCanonicalCandidate]
    source_authority_fingerprint: str
    expected_source_authority_fingerprint: str
    model_versions_match: bool = True
    max_quantity_to_construct: int = 4096
    max_cached_quantities: int = 4
    prepare_quantities: Optional[
        Callable[[Sequence[int]], Mapping[int, PreparedCanonicalCandidate]]
    ] = None
    quantity_batch_size: int = 8
    shared_score_cache: Optional["SharedScoreCache"] = None
    comparison_authority: str = COMPARISON_AUTHORITY_OVERALL_V12
    _quantities: Dict[int, PreparedCanonicalCandidate] = field(default_factory=OrderedDict, init=False)
    _constructed_quantities: set[int] = field(default_factory=set, init=False)
    _evaluations: Dict[tuple[int, int], Dict[str, Any]] = field(default_factory=OrderedDict, init=False)
    evaluation_count: int = field(default=0, init=False)
    lowest_evaluated_price: Optional[int] = field(default=None, init=False)
    cache_hits: int = field(default=0, init=False)
    cache_misses: int = field(default=0, init=False)
    cache_evictions: int = field(default=0, init=False)
    max_resident_quantities: int = field(default=0, init=False)
    bracket_expansions: int = field(default=0, init=False)
    bracket_refinements: int = field(default=0, init=False)
    fallback_count: int = field(default=0, init=False)
    scoring_seconds: float = field(default=0.0, init=False)
    comparator_seconds: float = field(default=0.0, init=False)
    exactness_verification_seconds: float = field(default=0.0, init=False)
    batch_build_count: int = field(default=0, init=False)
    batch_quantity_count: int = field(default=0, init=False)
    batch_fallback_count: int = field(default=0, init=False)
    max_pending_batch_candidates: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.source_authority_fingerprint != self.expected_source_authority_fingerprint:
            raise BestOpenPriceSearchError("source-authority fingerprint mismatch")
        if not self.model_versions_match:
            raise BestOpenPriceSearchError("model-version identity mismatch")
        if min(self.budget_cents, self.current_price_cents, self.current_quantity) < 1:
            raise ValueError("budget, current price, and current quantity must be positive")
        if self.quantity_batch_size < 1:
            raise ValueError("quantity_batch_size must be positive")

    @property
    def is_leader(self) -> bool:
        return self.current_rank == 1

    def _candidate(self, quantity: int) -> PreparedCanonicalCandidate:
        if quantity in self._quantities:
            self.cache_hits += 1
            self._quantities.move_to_end(quantity)
            return self._quantities[quantity]
        candidate = self.prepare_quantity(quantity)
        self._store_candidate(quantity, candidate)
        self.cache_misses += 1
        return candidate

    def _store_candidate(self, quantity: int, candidate: PreparedCanonicalCandidate) -> None:
        if candidate.product_id != self.product_id or candidate.quantity != quantity:
            raise BestOpenPriceSearchError("quantity cache identity mismatch")
        self._quantities[quantity] = candidate
        self._constructed_quantities.add(quantity)
        while len(self._quantities) > self.max_cached_quantities:
            self._quantities.popitem(last=False)
            self.cache_evictions += 1
        self.max_resident_quantities = max(self.max_resident_quantities, len(self._quantities))

    def _prepare_batch(self, quantities: Sequence[int]) -> Dict[int, PreparedCanonicalCandidate]:
        requested = list(dict.fromkeys(int(q) for q in quantities))
        if self.prepare_quantities is None:
            return {q: self.prepare_quantity(q) for q in requested}
        try:
            prepared = dict(self.prepare_quantities(requested))
            if set(prepared) != set(requested):
                raise BestOpenPriceSearchError("quantity batch returned the wrong quantity set")
            for quantity, candidate in prepared.items():
                if candidate.product_id != self.product_id or candidate.quantity != quantity:
                    raise BestOpenPriceSearchError("quantity batch identity mismatch")
            self.batch_build_count += 1
            self.batch_quantity_count += len(requested)
            self._constructed_quantities.update(requested)
            self.cache_misses += len(requested)
            return prepared
        except Exception:
            # Correctness-first fallback: an optimized construction failure
            # never changes threshold semantics or creates an unavailable row.
            self.batch_fallback_count += 1
            legacy = {q: self.prepare_quantity(q) for q in requested}
            self._constructed_quantities.update(requested)
            self.cache_misses += len(requested)
            return legacy

    def _scan_quantity_range(self, start: int, stop: int) -> Optional[Dict[str, Any]]:
        if self.prepare_quantities is None:
            for quantity in range(start, stop + 1):
                self.bracket_refinements += 1
                solved = self._solve_interval(quantity)
                if solved is not None:
                    return solved
            return None
        # High quantities can have no positive-cent price at all. Do not
        # construct an outcome vector for an unreachable allocation.
        reachable = [q for q in range(start, stop + 1) if self._bounds(q) is not None]
        for block_start in range(0, len(reachable), self.quantity_batch_size):
            quantities = reachable[block_start:block_start + self.quantity_batch_size]
            pending = self._prepare_batch(quantities)
            self.max_pending_batch_candidates = max(
                self.max_pending_batch_candidates, len(pending)
            )
            for quantity in quantities:
                candidate = pending.pop(quantity)
                self._store_candidate(quantity, candidate)
                self.bracket_refinements += 1
                solved = self._solve_interval(quantity)
                if solved is not None:
                    return solved
        return None

    def evaluate_price(self, price_cents: int) -> Dict[str, Any]:
        if not 1 <= price_cents <= self.budget_cents:
            raise ValueError("candidate price is outside the positive-cent Full Market domain")
        if not self.is_leader and price_cents > self.current_price_cents:
            raise BestOpenPriceSearchError("non-leader search may not evaluate above current market")
        if self.is_leader and price_cents < self.current_price_cents:
            raise BestOpenPriceSearchError("leader search may not evaluate below current market")
        quantity = self.budget_cents // price_cents
        key = (quantity, price_cents)
        if key not in self._evaluations:
            candidate = self._candidate(quantity)
            if self.shared_score_cache is not None:
                evaluated = self.shared_score_cache.evaluate(
                    candidate, price_cents, self.benchmark, authority=self.comparison_authority,
                )
            else:
                evaluated = candidate.evaluate(
                    price_cents, self.benchmark, comparison_authority=self.comparison_authority,
                )
            self.scoring_seconds += float(evaluated.get("scoringSeconds") or 0.0)
            self.comparator_seconds += float(evaluated.get("comparatorSeconds") or 0.0)
            self.evaluation_count += 1
            self.lowest_evaluated_price = min(self.lowest_evaluated_price or price_cents, price_cents)
            self._evaluations[key] = evaluated
            # Exact cent verification is cheap but its diagnostic cache must
            # not grow with the entire price domain.
            while len(self._evaluations) > 2048:
                self._evaluations.popitem(last=False)
        return self._evaluations[key]

    def _bounds(self, quantity: int) -> Optional[tuple[int, int]]:
        low, high = quantity_price_interval_cents(self.budget_cents, quantity)
        if self.is_leader:
            low = max(low, self.current_price_cents)
        else:
            high = min(high, self.current_price_cents)
        return (low, high) if low <= high else None

    def _solve_interval(self, quantity: int) -> Optional[Dict[str, Any]]:
        """Highest winning cent in one fixed physical quantity interval.

        Financial/V12 monotonicity does not prove comparator monotonicity:
        rounded-score ties can be decided by committed capital in the opposite
        direction. Five sentinels cannot exclude a narrow winning island.
        Prepared scoring made this inexpensive, so inspect cents high-to-low
        and stop at the first actual canonical win. No outcome reconstruction
        or sort occurs per price. The evaluation cache remains bounded.
        """
        bounds = self._bounds(quantity)
        if bounds is None:
            return None
        low, high = bounds
        for price in range(high, low - 1, -1):
            result = self.evaluate_price(price)
            if result["wins"]:
                return result
        return None

    def search(self) -> Dict[str, Any]:
        started = time.perf_counter()
        result = self._search_leader() if self.is_leader else self._search_non_leader()
        if result is None:
            return self._payload("unresolved_extreme_quantity", None, started)
        # Global one-cent maximality, including a quantity boundary.
        verification_started = time.perf_counter()
        price = int(result["priceCents"])
        if not result["wins"]:
            raise BestOpenPriceSearchError("returned threshold does not win")
        if price < self.budget_cents:
            if (not self.is_leader and price + 1 <= self.current_price_cents) or self.is_leader:
                if self.evaluate_price(price + 1)["wins"]:
                    raise BestOpenPriceSearchError("returned threshold is not maximal by one cent")
        self.exactness_verification_seconds += time.perf_counter() - verification_started
        payload = self._payload("exact", result, started)
        next_price = price + 1 if price < self.budget_cents else None
        next_wins = None
        if next_price is not None and (self.is_leader or next_price <= self.current_price_cents):
            next_wins = bool(self.evaluate_price(next_price)["wins"])
        low, high = quantity_price_interval_cents(self.budget_cents, int(result["quantity"]))
        payload["exactness"] = {
            "thresholdWins": True, "nextPriceCents": next_price,
            "nextPriceWins": next_wins,
            "oneCentMaximal": next_wins is not True,
            "quantityIntervalLowCents": low, "quantityIntervalHighCents": high,
            "nextCentCrossesQuantityBoundary": (
                next_price is not None and self.budget_cents // next_price != int(result["quantity"])
            ),
        }
        return payload

    def _search_non_leader(self) -> Optional[Dict[str, Any]]:
        # Ascending q means descending, disjoint price intervals. The first
        # winning interval therefore contains the GLOBAL highest allowed cent.
        # Bracketing is only an upper-bound optimization, never a proof that
        # unsampled intervals do not contain a winner.
        max_q = min(self.budget_cents, self.max_quantity_to_construct)
        q0 = self.budget_cents // self.current_price_cents
        if q0 > max_q:
            return None
        current_interval = self._solve_interval(q0)
        if current_interval is not None:
            return current_interval
        step = 1
        stop = max_q
        while q0 + step <= max_q:
            self.bracket_expansions += 1
            quantity = q0 + step
            bounds = self._bounds(quantity)
            if bounds and self.evaluate_price(bounds[0])["wins"]:
                stop = quantity
                break
            step *= 2
        return self._scan_quantity_range(q0 + 1, stop)

    def _search_leader(self) -> Optional[Dict[str, Any]]:
        q0 = self.budget_cents // self.current_price_cents
        if q0 > self.max_quantity_to_construct:
            return None
        if not self.evaluate_price(self.current_price_cents)["wins"]:
            raise BestOpenPriceSearchError("published current leader does not reconstruct as #1")
        # A first loss is only a local boundary. A different quantity can win
        # again at a higher price; inspect all higher-price intervals first.
        return self._scan_quantity_range(1, q0)

    def _payload(self, status: str, result: Optional[Mapping[str, Any]], started: float) -> Dict[str, Any]:
        return {"methodVersion": BEST_OPEN_PRICE_METHOD_VERSION, "status": status,
                "productId": self.product_id, "currentRank": self.current_rank,
                "currentPriceCents": self.current_price_cents,
                "threshold": dict(result) if result else None,
                "benchmarkProductId": self.benchmark.get("sealedProductId"),
                "benchmarkOverallRipV12Score": self.benchmark.get("overallRipV12Score"),
                "evaluationCount": self.evaluation_count,
                "physicalQuantitiesConstructed": sorted(self._constructed_quantities),
                "quantityCacheHits": self.cache_hits, "quantityCacheMisses": self.cache_misses,
                "quantityCacheEvictions": self.cache_evictions,
                "maximumResidentQuantities": self.max_resident_quantities,
                "bracketExpansions": self.bracket_expansions,
                "bracketRefinements": self.bracket_refinements,
                "monotonicityFallbackCount": self.fallback_count,
                "minimumQuantityInspected": min(self._constructed_quantities) if self._constructed_quantities else None,
                "maximumQuantityInspected": max(self._constructed_quantities) if self._constructed_quantities else None,
                "lowestCandidatePriceCents": self.lowest_evaluated_price,
                "candidateScoringSeconds": self.scoring_seconds,
                "comparatorSeconds": self.comparator_seconds,
                "exactnessVerificationSeconds": self.exactness_verification_seconds,
                "quantityBatchBuilds": self.batch_build_count,
                "quantityBatchQuantities": self.batch_quantity_count,
                "quantityBatchFallbacks": self.batch_fallback_count,
                "maximumPendingBatchCandidates": self.max_pending_batch_candidates,
                "wallSeconds": time.perf_counter() - started}

    def clear(self) -> None:
        self._evaluations.clear()
        self._quantities.clear()
        self._constructed_quantities.clear()


@dataclass
class DualBestOpenPriceSearch:
    """Runs the RIP (OVERALL_V12) and Financial (FINANCIAL_V4) exact searches
    for one product, sharing one SharedScoreCache and one quantity-level
    candidate cache so neither the expensive PreparedFinancialRipDistribution
    construction nor an identical (quantity, price_cents) score is ever
    duplicated between the two searches. Never runs the two V1 exact-search
    mathematics differently -- it constructs two ordinary
    ExactBestOpenPriceSearch instances and lets each run its own unmodified
    search().
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
    max_cached_quantities: int = 4
    quantity_batch_size: int = 8
    max_score_cache_entries: int = 4096

    def _shared_prepare_quantity(self, cache: Dict[int, PreparedCanonicalCandidate]) -> Callable[[int], PreparedCanonicalCandidate]:
        def prepare(quantity: int) -> PreparedCanonicalCandidate:
            if quantity not in cache:
                cache[quantity] = self.prepare_quantity(quantity)
            return cache[quantity]
        return prepare

    def _shared_prepare_quantities(
        self, cache: Dict[int, PreparedCanonicalCandidate]
    ) -> Optional[Callable[[Sequence[int]], Mapping[int, PreparedCanonicalCandidate]]]:
        if self.prepare_quantities is None:
            return None

        def prepare_batch(quantities: Sequence[int]) -> Mapping[int, PreparedCanonicalCandidate]:
            missing = [q for q in quantities if q not in cache]
            if missing:
                built = self.prepare_quantities(missing)
                cache.update(built)
            return {q: cache[q] for q in quantities}

        return prepare_batch

    def search(self) -> Dict[str, Any]:
        # One quantity-level memo shared by BOTH engines: whichever search
        # touches a given physical quantity first builds it; the other reuses
        # the same PreparedCanonicalCandidate object.
        quantity_cache: Dict[int, PreparedCanonicalCandidate] = {}
        shared_prepare_quantity = self._shared_prepare_quantity(quantity_cache)
        shared_prepare_quantities = self._shared_prepare_quantities(quantity_cache)
        score_cache = SharedScoreCache(max_entries=self.max_score_cache_entries)

        rip_engine = ExactBestOpenPriceSearch(
            product_id=self.product_id, budget_cents=self.budget_cents,
            current_price_cents=self.current_price_cents, current_quantity=self.current_quantity,
            current_rank=self.rip_current_rank, benchmark=self.rip_benchmark,
            prepare_quantity=shared_prepare_quantity,
            source_authority_fingerprint=self.source_authority_fingerprint,
            expected_source_authority_fingerprint=self.expected_source_authority_fingerprint,
            prepare_quantities=shared_prepare_quantities,
            max_quantity_to_construct=self.max_quantity_to_construct,
            max_cached_quantities=self.max_cached_quantities,
            quantity_batch_size=self.quantity_batch_size,
            shared_score_cache=score_cache,
            comparison_authority=COMPARISON_AUTHORITY_OVERALL_V12,
        )
        financial_engine = ExactBestOpenPriceSearch(
            product_id=self.product_id, budget_cents=self.budget_cents,
            current_price_cents=self.current_price_cents, current_quantity=self.current_quantity,
            current_rank=self.financial_current_rank, benchmark=self.financial_benchmark,
            prepare_quantity=shared_prepare_quantity,
            source_authority_fingerprint=self.source_authority_fingerprint,
            expected_source_authority_fingerprint=self.expected_source_authority_fingerprint,
            prepare_quantities=shared_prepare_quantities,
            max_quantity_to_construct=self.max_quantity_to_construct,
            max_cached_quantities=self.max_cached_quantities,
            quantity_batch_size=self.quantity_batch_size,
            shared_score_cache=score_cache,
            comparison_authority=COMPARISON_AUTHORITY_FINANCIAL_V4,
        )

        rip_result = rip_engine.search()
        financial_result = financial_engine.search()

        naive_score_count = rip_engine.evaluation_count + financial_engine.evaluation_count
        cache_diagnostics = score_cache.diagnostics()
        diagnostics = {
            **cache_diagnostics,
            "uniqueQuantitiesConstructed": len(quantity_cache),
            "naiveScoreCount": naive_score_count,
            "scoreReuseSavings": naive_score_count - cache_diagnostics["uniqueCandidatePricesScored"],
        }
        return {"ripResult": rip_result, "financialResult": financial_result, "diagnostics": diagnostics}
