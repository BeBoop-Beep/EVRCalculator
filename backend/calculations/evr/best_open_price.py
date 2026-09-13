"""Internal exact-cent Best-Open Price search infrastructure (no persistence)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional

from backend.calculations.evr.budget_normalized_product_ranking import (
    SORT_AUTHORITY_V12,
    rank_budget_cohort,
)
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.financial_rip_v4 import project_financial_rip_v4_from_v3_payload
from backend.desirability.weighted_rip import compute_overall_rip_v12

BEST_OPEN_PRICE_METHOD_VERSION = "budget_product_best_open_price_full_market_v1"


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

    def evaluate(self, price_cents: int, benchmark: Mapping[str, Any]) -> Dict[str, Any]:
        capital = self.quantity * price_cents / 100.0
        kwargs = {} if not self.min_simulation_count else {"min_simulation_count": self.min_simulation_count}
        v3 = self.distribution.score(capital, **kwargs)
        v4 = project_financial_rip_v4_from_v3_payload(v3)
        v12 = compute_overall_rip_v12(
            v4.get("score"), self.chase_accessibility_raw, self.collector_appeal_score
        )
        raw = {key: record.get("raw") for key, record in
               ((v3.get("audit") or {}).get("normalizedInputs") or {}).items()}
        candidate = {
            "sealedProductId": self.product_id,
            "targetBudget": self.target_budget,
            "actualCommittedCapital": capital,
            "financialRipV4Score": v4.get("score"),
            "overallRipV12Score": v12.get("score"),
            "overallRipV12Rankable": bool(v12.get("rankable")),
            "chanceToRecoverCapital": raw.get("true_win_probability"),
        }
        ranked = rank_budget_cohort([candidate, dict(benchmark)], sort_authority=SORT_AUTHORITY_V12)
        wins = bool(ranked and ranked[0]["sealedProductId"] == self.product_id)
        return {"wins": wins, "priceCents": price_cents, "quantity": self.quantity,
                "financialRipV3Score": v3.get("score"), "financialRipV4Score": v4.get("score"),
                "overallRipV12Score": v12.get("score"),
                "chanceToRecoverCapital": raw.get("true_win_probability"),
                "actualCommittedCapital": capital}


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
    _quantities: Dict[int, PreparedCanonicalCandidate] = field(default_factory=dict, init=False)
    _evaluations: Dict[tuple[int, int], Dict[str, Any]] = field(default_factory=dict, init=False)
    cache_hits: int = field(default=0, init=False)
    cache_misses: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.source_authority_fingerprint != self.expected_source_authority_fingerprint:
            raise BestOpenPriceSearchError("source-authority fingerprint mismatch")
        if not self.model_versions_match:
            raise BestOpenPriceSearchError("model-version identity mismatch")
        if min(self.budget_cents, self.current_price_cents, self.current_quantity) < 1:
            raise ValueError("budget, current price, and current quantity must be positive")

    @property
    def is_leader(self) -> bool:
        return self.current_rank == 1

    def _candidate(self, quantity: int) -> PreparedCanonicalCandidate:
        if quantity in self._quantities:
            self.cache_hits += 1
            return self._quantities[quantity]
        candidate = self.prepare_quantity(quantity)
        if candidate.product_id != self.product_id or candidate.quantity != quantity:
            raise BestOpenPriceSearchError("quantity cache identity mismatch")
        self._quantities[quantity] = candidate
        self.cache_misses += 1
        return candidate

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
            self._evaluations[key] = self._candidate(quantity).evaluate(price_cents, self.benchmark)
        return self._evaluations[key]

    def _bounds(self, quantity: int) -> Optional[tuple[int, int]]:
        low, high = quantity_price_interval_cents(self.budget_cents, quantity)
        if self.is_leader:
            low = max(low, self.current_price_cents)
        else:
            high = min(high, self.current_price_cents)
        return (low, high) if low <= high else None

    def _solve_interval(self, quantity: int) -> Optional[Dict[str, Any]]:
        bounds = self._bounds(quantity)
        if bounds is None:
            return None
        low, high = bounds
        low_result = self.evaluate_price(low)
        if not low_result["wins"]:
            return None
        high_result = self.evaluate_price(high)
        if high_result["wins"]:
            return high_result
        left, right = low, high
        while left < right:
            middle = (left + right + 1) // 2
            if self.evaluate_price(middle)["wins"]:
                left = middle
            else:
                right = middle - 1
        result = self.evaluate_price(left)
        next_result = self.evaluate_price(left + 1) if left < high else None
        if not result["wins"] or (next_result and next_result["wins"]):
            # Correctness-preserving fallback: enumerate this finite cent interval.
            winners = [self.evaluate_price(c) for c in range(low, high + 1)
                       if self.evaluate_price(c)["wins"]]
            return max(winners, key=lambda row: row["priceCents"]) if winners else None
        return result

    def search(self) -> Dict[str, Any]:
        started = time.perf_counter()
        result = self._search_leader() if self.is_leader else self._search_non_leader()
        if result is None:
            return self._payload("unresolved_extreme_quantity", None, started)
        # Global one-cent maximality, including a quantity boundary.
        price = int(result["priceCents"])
        if not result["wins"]:
            raise BestOpenPriceSearchError("returned threshold does not win")
        if price < self.budget_cents:
            if (not self.is_leader and price + 1 <= self.current_price_cents) or self.is_leader:
                if self.evaluate_price(price + 1)["wins"]:
                    raise BestOpenPriceSearchError("returned threshold is not maximal by one cent")
        return self._payload("exact", result, started)

    def _search_non_leader(self) -> Optional[Dict[str, Any]]:
        # This is a compute guard, not a price floor: crossing it returns an
        # explicit unresolved result and never fabricates a threshold.
        max_q = min(self.budget_cents, self.max_quantity_to_construct)
        q0 = self.budget_cents // self.current_price_cents
        tested = {q0}
        step = 1
        winning_q: Optional[int] = None
        while q0 + step <= max_q:
            q = q0 + step
            tested.add(q)
            bounds = self._bounds(q)
            if bounds and self.evaluate_price(bounds[0])["wins"]:
                winning_q = q
                break
            step *= 2
        if winning_q is None and q0 + step > max_q:
            q = max_q
            tested.add(q)
            bounds = self._bounds(q)
            if bounds and self.evaluate_price(bounds[0])["wins"]:
                winning_q = q
        if winning_q is None:
            return None
        # Exact bracket refinement: locate the first winning quantity interval.
        for q in range(q0, winning_q + 1):
            solved = self._solve_interval(q)
            if solved is not None:
                return solved
        return None

    def _search_leader(self) -> Optional[Dict[str, Any]]:
        current = self.evaluate_price(self.current_price_cents)
        if not current["wins"]:
            raise BestOpenPriceSearchError("published current leader does not reconstruct as #1")
        last_winning_price = self.current_price_cents
        step = 1
        first_losing_price: Optional[int] = None
        while self.current_price_cents + step <= self.budget_cents:
            price = self.current_price_cents + step
            probed = self.evaluate_price(price)
            if not probed["wins"]:
                first_losing_price = price
                break
            last_winning_price = price
            current = probed
            step *= 2
        if first_losing_price is None:
            at_budget = self.evaluate_price(self.budget_cents)
            if at_budget["wins"]:
                return at_budget
            first_losing_price = self.budget_cents
        left, right = last_winning_price, first_losing_price - 1
        while left < right:
            middle = (left + right + 1) // 2
            if self.evaluate_price(middle)["wins"]:
                left = middle
            else:
                right = middle - 1
        result = self.evaluate_price(left)
        if left < self.budget_cents and self.evaluate_price(left + 1)["wins"]:
            winners = [self.evaluate_price(c) for c in range(last_winning_price, first_losing_price + 1)
                       if self.evaluate_price(c)["wins"]]
            return max(winners, key=lambda row: row["priceCents"])
        return result

    def _payload(self, status: str, result: Optional[Mapping[str, Any]], started: float) -> Dict[str, Any]:
        return {"methodVersion": BEST_OPEN_PRICE_METHOD_VERSION, "status": status,
                "productId": self.product_id, "currentRank": self.current_rank,
                "currentPriceCents": self.current_price_cents,
                "threshold": dict(result) if result else None,
                "benchmarkProductId": self.benchmark.get("sealedProductId"),
                "evaluationCount": len(self._evaluations),
                "physicalQuantitiesConstructed": sorted(self._quantities),
                "quantityCacheHits": self.cache_hits, "quantityCacheMisses": self.cache_misses,
                "wallSeconds": time.perf_counter() - started}

    def clear(self) -> None:
        self._evaluations.clear()
        self._quantities.clear()
