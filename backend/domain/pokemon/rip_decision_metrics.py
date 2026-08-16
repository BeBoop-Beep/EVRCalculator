"""Display math for the RIP decision layer.

WHAT THIS IS
------------
Direct, reversible transformations of numbers that ALREADY exist on
``simulation_sealed_product_results`` (expected value, market cost) and
``simulation_input_cards`` (the modeled per-pack pull rate). Every function here
is pure: no database, no run resolution, no policy.

WHAT THIS DELIBERATELY IS NOT
-----------------------------
* NOT a score. Nothing here is fitted, weighted, calibrated or normalized, and
  nothing here may be ranked. ``modelEdgePercent`` is arithmetic on two
  published numbers, not a verdict about a product.
* NOT a recommendation. A negative edge is not "a bad buy" and a positive edge
  is not "a good buy" - the model prices a long-run opening expectation, not an
  outcome, and this module says nothing about either.
* NOT persisted. These are derived at read/publication time precisely so they
  can never drift from the two authoritative columns they come from.

MISSING INPUTS STAY MISSING
---------------------------
Every function returns ``None`` rather than a placeholder when its input is
absent, non-numeric, non-finite or out of domain. A fabricated ``0.0`` ratio is
indistinguishable on a page from a real one, which makes it the more dangerous
of the two failure modes.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

RIP_DECISION_METRICS_VERSION = "rip-decision-metrics-v1"

#: Ratios and percentages are rounded only to strip IEEE-754 representation
#: noise (``10.5 / 10.0 * 100`` is ``105.00000000000001``). The precision is far
#: beyond any display need, so this never changes a displayed value.
_RATIO_PRECISION = 12
_PERCENT_PRECISION = 10


def _finite_float(value: Any) -> Optional[float]:
    """``value`` as a finite float, or ``None``. Booleans are not numbers here."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _non_negative(value: Any) -> Optional[float]:
    number = _finite_float(value)
    if number is None or number < 0.0:
        return None
    return number


def _positive(value: Any) -> Optional[float]:
    number = _finite_float(value)
    if number is None or number <= 0.0:
        return None
    return number


# ---------------------------------------------------------------------------
# Sealed product decision metrics
# ---------------------------------------------------------------------------

def product_decision_metrics(
    *, expected_value: Any, product_market_cost: Any
) -> Dict[str, Optional[float]]:
    """The four decision numbers derived from one product's EV and market cost.

    ``modelBreakEvenPrice`` IS ``expected_value`` - the same long-run modeled
    opening value, expressed as the market price at which modeled EV would equal
    the purchase price. It is not a second model and carries no new assumption.

    It survives a missing market cost on purpose: what a product is worth to open
    does not depend on what it currently sells for. The three ratio metrics do,
    and become ``None`` together when the cost is missing or non-positive.
    """
    break_even = _non_negative(expected_value)
    cost = _positive(product_market_cost)

    if break_even is None or cost is None:
        return {
            "modelBreakEvenPrice": break_even,
            "modeledReturnRatio": None,
            "modeledReturnPercent": None,
            "modelEdgePercent": None,
        }

    ratio = round(break_even / cost, _RATIO_PRECISION)
    return {
        "modelBreakEvenPrice": break_even,
        "modeledReturnRatio": ratio,
        "modeledReturnPercent": round(ratio * 100.0, _PERCENT_PRECISION),
        "modelEdgePercent": round((ratio - 1.0) * 100.0, _PERCENT_PRECISION),
    }


# ---------------------------------------------------------------------------
# Exact-card cumulative probability
# ---------------------------------------------------------------------------

def implied_odds_one_in_n(probability: Any) -> Optional[float]:
    """``1 / p`` - the "one in N packs" form of a modeled per-pack pull rate."""
    p = _positive(probability)
    if p is None:
        return None
    return round(1.0 / p, _RATIO_PRECISION)


def packs_for_cumulative_probability(probability: Any, target: float) -> Optional[int]:
    """Packs needed for cumulative probability ``target`` at per-pack rate ``p``.

    ``ceil(log(1 - target) / log(1 - p))``, the standard independent-trials
    result. Independence across packs is the simulation's own assumption, so this
    introduces none of its own.

    Boundaries are answered rather than crashed: a non-positive or missing rate
    is unavailable (no number of packs makes an impossible pull happen), and a
    rate of 1 or more is satisfied by a single pack.
    """
    q = _finite_float(target)
    if q is None or not 0.0 < q < 1.0:
        return None
    p = _positive(probability)
    if p is None:
        return None
    if p >= 1.0:
        return 1
    packs = math.ceil(math.log(1.0 - q) / math.log(1.0 - p))
    return max(1, int(packs))


def exact_card_probability_contract(probability: Any) -> Dict[str, Optional[float]]:
    """The JSON-safe modeled-odds block for one card.

    These are MODELED odds under the run's pull-rate assumptions, not guarantees
    about any real pack. No key here is ever ``Infinity`` or ``NaN``.
    """
    p = _positive(probability)
    return {
        "modeledProbability": p,
        "impliedOddsOneInN": implied_odds_one_in_n(p),
        "packsFor50PercentChance": packs_for_cumulative_probability(p, 0.50),
        "packsFor90PercentChance": packs_for_cumulative_probability(p, 0.90),
    }
