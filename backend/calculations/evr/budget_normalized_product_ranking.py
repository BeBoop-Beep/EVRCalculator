"""Budget-Normalized Product Ranking — the internal, cross-format capital-matched
ranking engine.

WHAT THIS IS
------------
The validated answer to "if I have about $X to spend, which eligible sealed
product opening strategy performs best" — using WHOLE purchasable retail
units at a stated committed-capital level, never a natural-unit cross-format
sort of ``overall_rip_v10_score`` (that comparison remains invalid; see
``backend.domain.pokemon.sealed_product_comparison_scope``).

This is NOT a context-free universal "Overall Product Rank". Research
(``docs/research/OVERALL_PRODUCT_RANK_DECISION_2026-08-22_v2.md``) found no
single budget gives 100% cohort coverage, so every rank produced here is
explicitly budget-qualified — the budget is part of the rank's identity, not
an implementation detail. This module is INTERNAL infrastructure for a future
higher-tier "given my budget, what should I open" capability. It is not wired
to any current customer-facing surface.

RANKING METHOD VERSION
-----------------------
``BUDGET_NORMALIZED_RANKING_METHOD_VERSION`` below. Bump it (and add a new
constant, never mutate the meaning of an existing one — matching the
project's convention for every other RIP model version) if the allocation
rule, scoring chain, or comparator change.

ALLOCATION RULE (validated in this task; see decision record)
---------------------------------------------------------------
``quantity = floor(target_budget / product_market_price)``, i.e. the largest
whole number of retail units purchasable without exceeding the target. This
is Candidate A from the research phase ("simple floor quantity") — chosen
over a nearest-whole-unit-within-tolerance search because floor quantity is:
simpler to explain to a user ("as many as $X buys"), deterministic with no
search/tolerance parameter to tune, and the SAME rule the existing validated
equal-spend research already used for its `fixed_budget_quantity` bands
(preserving continuity with the already-validated $25-$500 research). A
product priced above the target budget is simply ineligible (quantity 0),
recorded as such rather than silently dropped.

Leftover ("unused") capital is recorded explicitly and NEVER treated as
spent, invested, or folded into the outcome distribution.

SCORING CHAIN (mirrors production exactly)
-------------------------------------------
For a strategy of quantity Q of one SKU: build the REAL Q-unit outcome
distribution (reusing ``build_stage1_product_distributions`` — the same
machinery Stage 1/2 production scoring and the equal-spend research use, so
no approximation of "single-unit metrics x Q"), add guaranteed-component
value once per unit purchased, then score via
``build_financial_rip_v3`` -> ``project_financial_rip_v4_from_v3_payload``
(the same V3-then-project-to-V4 chain production uses — verified by exact
reconstruction in the equal-spend V4 research), then
``compute_overall_rip_v10(financial_v4_score, collector_appeal_score)`` using
the SAME Collector Appeal score the SKU's set already carries (Collector
Appeal describes the set's desirability, not purchase quantity, and is never
recomputed here).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v4 import (
    project_financial_rip_v4_from_v3_payload,
)
from backend.calculations.evr.guaranteed_component_value import (
    add_guaranteed_components,
)
from backend.calculations.evr.sealed_product_distribution import (
    build_stage1_product_distributions,
)
from backend.desirability.composite import assign_composite_tier
from backend.desirability.weighted_rip import compute_overall_rip_v10

#: Bump on any change to allocation rule, scoring chain, or comparator.
#: Never mutate the meaning of an already-published version string.
BUDGET_NORMALIZED_RANKING_METHOD_VERSION = "budget_product_ranking_v1"
ALLOCATION_METHOD_VERSION = "budget_allocation_floor_quantity_v1"

#: Comparison-scope identity for THIS ranking — deliberately distinct from
#: the natural-unit `within_product_family_only` scope, which is untouched.
BUDGET_COMPARISON_SCOPE_VERSION = "equal_committed_capital_cross_format_v1"

#: Validated in research (docs/research/OVERALL_PRODUCT_RANK_DECISION_2026-08-22_v2.md):
#: near-perfect (median Spearman 1.0) cross-budget rank stability, zero
#: dominance inversions. Preserved as the canonical standard bands.
CANONICAL_BUDGET_BANDS: tuple[float, ...] = (25.0, 50.0, 100.0, 150.0, 250.0, 500.0)

#: FULL_MARKET is a sentinel budget_type, not a fixed dollar figure — its
#: dollar value is resolved dynamically per publication (see
#: `resolve_full_market_budget`) and stored alongside every record built at
#: it, so a future price movement crossing the rounding boundary is
#: reproducible and auditable rather than silently inconsistent.
BUDGET_TYPE_STANDARD = "standard_band"
BUDGET_TYPE_FULL_MARKET = "full_market"
BUDGET_TYPE_CUSTOM = "custom"

#: The Full Market anchor rounds the current maximum eligible SKU price UP to
#: the next $50 increment. Chosen over $25 (same anchor value on the current
#: cohort — no coverage/inflation benefit, but a smaller boundary means MORE
#: frequent anchor changes as prices drift) and over $100 (needlessly
#: inflates committed capital ~4.5x more than necessary on the current
#: cohort, with no stability benefit measured). See decision record for the
#: comparison.
FULL_MARKET_ROUNDING_INCREMENT = 50.0


def resolve_full_market_budget(eligible_market_prices: Sequence[float]) -> Dict[str, Any]:
    """The lowest standardized committed-capital level admitting every eligible SKU.

    Deliberately NOT the raw maximum price: rounds up to the nearest
    ``FULL_MARKET_ROUNDING_INCREMENT`` so the anchor does not move every time
    the single most expensive SKU's price changes by a few dollars, while a
    price change that does NOT cross the rounding boundary produces the
    identical anchor (reproducible, low-sensitivity).
    """
    prices = [float(p) for p in eligible_market_prices if p is not None and float(p) > 0]
    if not prices:
        raise ValueError("cannot resolve a Full Market budget with no eligible priced products")
    max_price = max(prices)
    increment = FULL_MARKET_ROUNDING_INCREMENT
    anchor = math.ceil(max_price / increment) * increment
    # A max price that lands exactly on a boundary must still admit that SKU
    # (floor-quantity needs budget >= price to buy 1 unit).
    if anchor < max_price:
        anchor += increment
    return {
        "budget": float(anchor),
        "maxEligibleSkuPrice": max_price,
        "roundingIncrement": increment,
        "roundingRule": f"ceil(maxEligibleSkuPrice / {increment:g}) * {increment:g}",
    }


def whole_unit_allocation(target_budget: float, product_market_price: float) -> Dict[str, Any]:
    """Whole-unit floor allocation. See module docstring for why floor, not nearest-search."""
    price = float(product_market_price)
    if price <= 0:
        raise ValueError("product_market_price must be positive")
    budget = float(target_budget)
    if budget <= 0:
        raise ValueError("target_budget must be positive")
    quantity = int(math.floor(budget / price))
    actual_committed_capital = quantity * price
    unused_capital = budget - actual_committed_capital
    unused_capital_percent = (unused_capital / budget) if budget > 0 else None
    return {
        "eligible": quantity >= 1,
        "quantity": quantity,
        "targetBudget": budget,
        "actualCommittedCapital": actual_committed_capital,
        "unusedCapital": unused_capital,
        "unusedCapitalPercent": unused_capital_percent,
    }


def build_budget_strategy_values(
    *,
    base_random_pack_values: np.ndarray,
    quantity: int,
    guaranteed_component_market_value: Optional[float],
    canonical_set_key: Any,
    run_fingerprint: Optional[str] = None,
) -> np.ndarray:
    """The REAL quantity-Q outcome vector: not `single_unit_metric * Q`.

    ``base_random_pack_values`` is the single-unit random-component
    distribution (already built once per set/pack-count by the caller and
    reused across every candidate budget/product, exactly like the
    equal-spend research's `StrategyEngine` cache). Guaranteed-component
    value is added once PER UNIT purchased, matching how a real multi-unit
    purchase accumulates guaranteed contents.
    """
    if quantity < 1:
        raise ValueError("quantity must be a positive whole retail unit")
    if quantity == 1:
        values = base_random_pack_values
    else:
        built = build_stage1_product_distributions(
            base_random_pack_values,
            pack_counts=[quantity],
            canonical_set_key=canonical_set_key,
            run_fingerprint=run_fingerprint,
        )
        values = built["distributions"][quantity]
    if guaranteed_component_market_value:
        values = add_guaranteed_components(values, float(guaranteed_component_market_value) * quantity)
    return values


def score_budget_strategy(
    values: np.ndarray,
    actual_committed_capital: float,
    collector_appeal_score: Optional[float],
    *,
    min_simulation_count: int = 0,
) -> Dict[str, Any]:
    """Financial RIP V4 (projected from V3, exactly as production computes it),
    then Overall RIP V10 from that V4 score and the SAME Collector Appeal
    score the set already carries (never recomputed per quantity)."""
    v3_kwargs = {} if not min_simulation_count else {"min_simulation_count": min_simulation_count}
    v3_payload = build_financial_rip_v3(values, actual_committed_capital, **v3_kwargs)
    v4_payload = project_financial_rip_v4_from_v3_payload(v3_payload)
    financial_v4_score = v4_payload.get("score")
    financial_v4_status = v4_payload.get("status")
    financial_v4_rankable = bool(v4_payload.get("rankable"))
    overall_v10 = None
    if financial_v4_rankable and financial_v4_score is not None and collector_appeal_score is not None:
        overall_v10 = compute_overall_rip_v10(financial_v4_score, collector_appeal_score)
    return {
        "financialRipV4Score": financial_v4_score,
        "financialRipV4Status": financial_v4_status,
        "financialRipV4Rankable": financial_v4_rankable,
        "financialRipV4Payload": v4_payload,
        "overallRipV10Score": overall_v10.get("score") if overall_v10 else None,
        "overallRipV10Rankable": bool(overall_v10.get("rankable")) if overall_v10 else False,
        "overallRipV10Version": overall_v10.get("version") if overall_v10 else None,
        "expectedValue": float(np.mean(values)),
        "medianValue": float(np.median(values)),
    }


def _tier_sort_key(entry: Mapping[str, Any]) -> tuple:
    """Overall RIP V10 (desc) -> Financial RIP V4 (desc) -> chance-to-recover
    (desc, when present) -> committed-capital closeness to target (asc) ->
    sealed_product_id (deterministic final tie-break). Mirrors the validated
    Family Rank comparator's structure so the two ranking systems read
    consistently, adapted with a capital-closeness tie-break specific to
    budget matching."""
    overall = entry.get("overallRipV10Score")
    financial = entry.get("financialRipV4Score")
    recover = entry.get("chanceToRecoverCost")
    mismatch = abs(entry.get("actualCommittedCapital", 0.0) - entry.get("targetBudget", 0.0))
    return (
        -(overall if overall is not None else float("-inf")),
        -(financial if financial is not None else float("-inf")),
        -(recover if recover is not None else float("-inf")),
        mismatch,
        str(entry.get("sealedProductId") or ""),
    )


def rank_budget_cohort(strategies: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Rank only the RANKABLE strategies (overallRipV10Score is not None).

    Ineligible/unrankable strategies are never assigned a rank; callers must
    keep them out of this list's cohort-size accounting and report them as
    excluded with a reason, never as a fabricated rank.
    """
    rankable = [s for s in strategies if s.get("overallRipV10Score") is not None]
    ordered = sorted(rankable, key=_tier_sort_key)
    size = len(ordered)
    out = []
    for index, entry in enumerate(ordered, start=1):
        out.append(
            {
                **entry,
                "budgetRank": index,
                "budgetCohortSize": size,
                "budgetTier": assign_composite_tier(entry["overallRipV10Score"]),
            }
        )
    return out
