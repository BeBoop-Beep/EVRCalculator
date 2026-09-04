"""Chase Access at Budget V1 - a PREMIUM, product-level, budget-dependent metric.

PRODUCTION MODULE (pure math only - no DB access, no HTTP, no persistence).

THIS MODULE DOES NOT REPLACE OR DUPLICATE `chase_accessibility.py`
-------------------------------------------------------------------
Chase Accessibility (``A_raw = sum_i HC_i * p_i``) stays exactly as it is: the
canonical SET-level metric, 4% of Overall RIP V12, computed once per set/run
by ``backend/desirability/chase_accessibility.py``. This module REUSES that
module's Chase Significance weighting (``compute_chase_significance`` /
``compute_mapped_hc_mass``) rather than reimplementing HC math, and adds
exactly one new, budget-dependent quantity on top of it:

    O_budget = sum_i HC_i * [1 - (1 - p_i)^n]

where ``n`` is the number of EFFECTIVE RANDOM PACKS a buyer's purchased
product quantity actually opens (see ``effective_random_packs`` below - this
is NOT ``budget / pack_price``).

WHAT O_budget IS AND IS NOT
----------------------------
It is the HC-weighted share of the set's important collectible value that
becomes REACHABLE through the packs a budget actually buys. It answers: "at
this budget, how much of this set's important value can this product make
reachable?"

It is NOT a "chance of pulling a chase card". There is no discrete chase
roster (see chase_accessibility.py's own docstring for why). O_budget is a
bounded [0, 1] weighted reachability index, not an event probability, even
though each per-card term ``1-(1-p_i)^n`` is itself a valid P(>=1 copy in n
independent packs) under the model's own IID assumption
(see backend/research/product_chase_economics/metrics.py:aggregate_to_product,
whose closed form this reuses at the per-card level instead of the per-product
level).

FAIL-CLOSED DISCIPLINE (identical to chase_accessibility.py)
--------------------------------------------------------------
* No price renormalisation.
* No missing-probability renormalisation.
* ``mapped_hc_mass < MIN_MAPPED_HC_MASS`` -> unavailable, never computed on a
  reduced/renormalised universe.
* A negative or non-finite pack count -> unavailable.
* ``n == 0`` (a strategy that genuinely buys zero packs) -> a real, published
  0.0, NOT unavailable. Zero packs opened means zero value was made reachable;
  that is a measured fact about the strategy, not a missing input.
* A missing/unsupported input (no probability coverage, no set universe, no
  pack count when a budget purchase clearly implies packs are being opened)
  -> unavailable, never a fabricated zero.

ECE (Efficiency per Effective Cost) - DESCRIPTIVE CONTEXT ONLY
-----------------------------------------------------------------
    ECE = A_raw / effective_pack_cost,  effective_pack_cost = product_market_cost / random_pack_count

Proven (docs/research/OVERALL_RIP_ACCESSIBILITY_PASS_1A_ECE.md,
OVERALL_RIP_ACCESSIBILITY_PASS_1A_PRODUCT_SUPPLEMENT.md) to be mechanically
equivalent to price-only ordering WITHIN one set: because ``A_raw`` is
constant across every product of the same set/run, ranking by ECE within a
set is identical to ranking by ``1 / effective_pack_cost`` - it carries zero
extra information for that comparison. COMPARABILITY POLICY (Phase 6):

* ECE MUST NEVER be used to power a universal All-Products ranking, a
  cross-format global leaderboard, Overall RIP, normal Plus product rankings,
  or the explicit-budget Chase Access cross-format authority (that is
  O_budget's job - see below).
* ECE MAY be shown as descriptive context in Premium product detail, and MAY
  be used to rank products WITHIN an explicitly, genuinely comparable family
  (e.g. same set, same product type) where a reader can trust "cheaper access
  per dollar" as a meaningful comparison. It is the caller's responsibility to
  supply only a genuinely comparable cohort; this module does not attempt to
  infer or validate family comparability itself, and family-level ECE ranking
  MUST be disabled rather than faked wherever the caller cannot assert a
  trustworthy comparable cohort.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.desirability.chase_accessibility import (
    MIN_MAPPED_HC_MASS,
    compute_chase_significance,
    compute_mapped_hc_mass,
)

#: The published model identity for O_budget. Stored on every row so a value
#: can never be read without the model that produced it.
PRODUCT_CHASE_ACCESS_VERSION = (
    "product_chase_access_v1_hc_weighted_budget_reachability_modeled_probability"
)

#: The ECE identity. Descriptive/context-only per the comparability policy above.
EFFICIENCY_PER_EFFECTIVE_COST_VERSION = "efficiency_per_effective_cost_v1_araw_over_pack_cost"

STATUS_READY = "ready"
STATUS_NO_PULL_MODEL = "unavailable_pull_model"
STATUS_LOW_COVERAGE = "chase_access_insufficient_probability_coverage"
STATUS_NO_UNIVERSE = "unavailable_no_drawable_universe"
STATUS_NO_PRICED_UNIVERSE = "unavailable_no_priced_universe"
STATUS_NO_PACK_COUNT = "unavailable_no_effective_pack_count"
STATUS_INVALID_PACK_COUNT = "unavailable_invalid_effective_pack_count"

STATUS_REASONS: Dict[str, str] = {
    STATUS_NO_PULL_MODEL: (
        "this set has no authoritative modeled pull probabilities, so Chase Access "
        "cannot be computed. A pull rate is never fabricated."),
    STATUS_LOW_COVERAGE: (
        "too much of this set's Chase Significance carries no value or no modeled "
        "probability. Unmapped significance is never renormalised away."),
    STATUS_NO_UNIVERSE: "no drawable card variants were supplied for this set.",
    STATUS_NO_PRICED_UNIVERSE: (
        "no drawable card variant carries a finite positive market value, so there is "
        "no value concentration to weight."),
    STATUS_NO_PACK_COUNT: (
        "no effective random pack count was supplied for this budget/product "
        "combination, so Chase Access is unavailable (never fabricated as zero)."),
    STATUS_INVALID_PACK_COUNT: (
        "the effective random pack count was negative or non-finite; Chase Access is "
        "unavailable rather than computed on an invalid quantity."),
}


class ProductChaseAccessInputError(ValueError):
    """Raised when inputs cannot describe one coherent set snapshot.

    Mirrors ``ChaseAccessibilityInputError``: a mixed set/run or duplicated
    variant is a CALLER defect, not a property of the set.
    """


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _finite_positive(value: Any) -> Optional[float]:
    number = _finite(value)
    return number if number is not None and number > 0.0 else None


def _finite_nonnegative(value: Any) -> Optional[float]:
    number = _finite(value)
    return number if number is not None and number >= 0.0 else None


def _valid_probability(value: Any) -> Optional[float]:
    number = _finite(value)
    if number is None or number < 0.0 or number > 1.0:
        return None
    return number


# --------------------------------------------------------------------------
# Phase 4 - what n means
# --------------------------------------------------------------------------

def effective_random_packs(*, quantity: Any, random_pack_count: Any) -> Optional[float]:
    """``n = quantity * random_pack_count`` for ONE product's purchased quantity.

    ``quantity`` is the ACTUAL whole-product quantity a budget strategy buys
    (e.g. the existing floor-quantity budget allocator's ``quantity`` field) -
    never re-derived here as ``budget / pack_price``. ``random_pack_count`` is
    the product's own canonical composition value (e.g. 1 for a loose booster,
    a booster box's real slot count, an ETB's real random-pack slot count
    excluding its guaranteed promo/accessory components). Guaranteed
    accessories must already be excluded from ``random_pack_count`` upstream
    by the canonical product composition source - this function performs no
    composition logic of its own.

    Returns ``None`` (unavailable, never a fabricated 0) when either input is
    missing, non-finite, or negative. A quantity or pack count of exactly 0 is
    a valid, real "zero packs opened" measurement and returns 0.0.
    """
    q = _finite_nonnegative(quantity)
    n = _finite_nonnegative(random_pack_count)
    if q is None or n is None:
        return None
    return q * n


# --------------------------------------------------------------------------
# Phase 3 - O_budget canonical math (pure, no DB access)
# --------------------------------------------------------------------------

def _unavailable(status: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "oBudget": None,
        "oBudgetPct": None,
        "status": status,
        "statusReason": STATUS_REASONS.get(status, ""),
        "publishable": False,
        "version": PRODUCT_CHASE_ACCESS_VERSION,
        "minMappedHcMass": MIN_MAPPED_HC_MASS,
    }
    payload.update(extra)
    return payload


def compute_o_budget(
    *,
    variants: Sequence[Mapping[str, Any]],
    effective_packs: Any,
    has_pull_model: bool = True,
    set_id: Optional[str] = None,
    calculation_run_id: Optional[str] = None,
    min_mapped_mass: float = MIN_MAPPED_HC_MASS,
) -> Dict[str, Any]:
    """``O_budget = sum_i HC_i * [1 - (1 - p_i)^n]`` for ONE set at ONE run.

    Keyword-only, mirroring ``compute_chase_accessibility``'s signature
    discipline. ``variants`` are the SAME same-run drawable
    ``simulation_card_variant_pull_rates`` rows Chase Accessibility itself
    reads - value and probability from the same row, no fan-out, no product
    input inside this universe (product-specific ``effective_packs`` is
    supplied once, externally, per Phase 4).

    ``p_i = modeled_probability`` ONLY - never ``effective_pull_rate`` (odds)
    and never a renormalised probability. No missing-probability
    renormalisation, no price renormalisation, and the identical
    ``mapped_hc_mass < min_mapped_mass`` fail-closed gate as Chase
    Accessibility. This function performs NO DB access.
    """
    if not has_pull_model:
        return _unavailable(STATUS_NO_PULL_MODEL, setId=set_id,
                            calculationRunId=calculation_run_id)
    if not variants:
        return _unavailable(STATUS_NO_UNIVERSE, setId=set_id,
                            calculationRunId=calculation_run_id, eligibleVariantCount=0)

    # ---- coherence: one set, one run, one row per variant -------------------
    set_ids = {str(row.get("set_id")) for row in variants if row.get("set_id") is not None}
    if len(set_ids) > 1:
        raise ProductChaseAccessInputError(
            "Chase Access describes one set; received %d: %s"
            % (len(set_ids), sorted(set_ids)[:5]))
    run_ids = {str(row.get("calculation_run_id")) for row in variants
               if row.get("calculation_run_id") is not None}
    if len(run_ids) > 1:
        raise ProductChaseAccessInputError(
            "Chase Access describes one calculation run; received %d: %s"
            % (len(run_ids), sorted(run_ids)[:5]))
    if calculation_run_id is not None and run_ids and str(calculation_run_id) not in run_ids:
        raise ProductChaseAccessInputError(
            "rows belong to run %s, not the requested %s"
            % (sorted(run_ids)[0], calculation_run_id))

    identities = [row.get("card_variant_id") for row in variants]
    if any(identity is None for identity in identities):
        raise ProductChaseAccessInputError("every row needs a card_variant_id")
    if len({str(identity) for identity in identities}) != len(identities):
        raise ProductChaseAccessInputError(
            "duplicate card_variant_id rows: Chase Significance would double-count them")

    # ---- pack-count gate: unavailable (never zero) unless genuinely 0 ------
    n = _finite_nonnegative(effective_packs)
    if effective_packs is None:
        return _unavailable(STATUS_NO_PACK_COUNT, setId=set_id,
                            calculationRunId=calculation_run_id)
    if n is None:
        return _unavailable(STATUS_INVALID_PACK_COUNT, setId=set_id,
                            calculationRunId=calculation_run_id)

    # ---- the full drawable priced universe (identical to Chase Accessibility) --
    values = [row.get("price_used") for row in variants]
    priced = [_finite_positive(value) is not None for value in values]
    priced_count = sum(priced)
    if priced_count == 0:
        return _unavailable(STATUS_NO_PRICED_UNIVERSE, setId=set_id,
                            calculationRunId=calculation_run_id,
                            eligibleVariantCount=len(variants), pricedVariantCount=0)

    probabilities = [_valid_probability(row.get("modeled_probability")) for row in variants]
    usable = [priced[i] and probabilities[i] is not None for i in range(len(variants))]
    mapped_mass = compute_mapped_hc_mass(values, usable)

    diagnostics = {
        "setId": set_id,
        "calculationRunId": calculation_run_id or (sorted(run_ids)[0] if run_ids else None),
        "eligibleVariantCount": len(variants),
        "pricedVariantCount": priced_count,
        "probabilityMappedVariantCount": sum(usable),
        "mappedHcMass": mapped_mass,
        "minMappedHcMass": min_mapped_mass,
        "effectivePacks": n,
    }

    if mapped_mass < min_mapped_mass:
        return _unavailable(STATUS_LOW_COVERAGE, unmappedHcMass=1.0 - mapped_mass,
                            **diagnostics)

    usable_values = [float(_finite_positive(values[i]))
                     for i in range(len(variants)) if usable[i]]
    usable_probabilities = [float(probabilities[i])
                            for i in range(len(variants)) if usable[i]]

    significance = compute_chase_significance(usable_values)

    if n == 0.0:
        # A real, measured zero: zero packs opened reaches zero value.
        o_budget = 0.0
    else:
        reach = [1.0 - (1.0 - p) ** n for p in usable_probabilities]
        o_budget = math.fsum(w * r for w, r in zip(significance, reach))

    return {
        "oBudget": o_budget,
        "oBudgetPct": o_budget * 100.0,
        "status": STATUS_READY,
        "statusReason": None,
        "publishable": True,
        "version": PRODUCT_CHASE_ACCESS_VERSION,
        "minMappedHcMass": min_mapped_mass,
        **diagnostics,
    }


# --------------------------------------------------------------------------
# Phase 6 - ECE (descriptive/context only - see module docstring policy)
# --------------------------------------------------------------------------

def effective_pack_cost(*, product_market_cost: Any, random_pack_count: Any) -> Optional[float]:
    """``effective_pack_cost = product_market_cost / random_pack_count``.

    Identical in spirit to Stage V-B's ``pack_equivalent_cost`` (see
    ``backend/research/product_chase_economics/contract.py``) - reimplemented
    here, not imported, because that module is explicitly RESEARCH ONLY and
    this is a production surface. Returns ``None`` (never fabricated) when
    either input is missing/non-positive.
    """
    cost = _finite_positive(product_market_cost)
    count = _finite_positive(random_pack_count)
    if cost is None or count is None:
        return None
    return cost / count


def compute_ece(*, a_raw: Any, effective_pack_cost_value: Any) -> Optional[float]:
    """``ECE = A_raw / effective_pack_cost``.

    DESCRIPTIVE/COMPARABLE-FAMILY-CONTEXT ONLY - see the comparability policy
    in this module's docstring and the permanent Phase 7 invariant test in
    ``test_product_chase_access.py``. This function performs no cohort
    validation; callers are responsible for only invoking it within a
    genuinely comparable family, and for never using its output to power a
    universal All-Products ranking, Overall RIP, or the budget cross-format
    Chase Access authority (``compute_o_budget`` is that authority).
    """
    a = _finite_nonnegative(a_raw)
    cost = _finite_positive(effective_pack_cost_value)
    if a is None or cost is None:
        return None
    return a / cost
