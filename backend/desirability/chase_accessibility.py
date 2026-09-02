"""Chase Accessibility V1 - a set-level published metric.

PRODUCTION MODULE. This is the canonical implementation; nothing here imports
from ``backend/research/``. The Stage XIV research module remains the historical
record and is not on any runtime path.

THE METRIC
----------
    HC_i    = V_i^2 / sum_j V_j^2          (Chase Significance)
    O_pack  = sum_i HC_i * p_i             (Chase Accessibility)

Equivalently, and computed both ways on every call as a parity check:

    O_pack  = sum_i V_i^2 p_i / sum_j V_j^2

    N_HC    = 1 / sum_i HC_i^2             (Chase Depth, an EFFECTIVE count)

Stage XIV's worst parity delta across 22 sets was 8.674e-19.

WHAT THIS IS, IN PLAIN ENGLISH
------------------------------
*How reachable is this set's most meaningful collectible value from a random
pack?* Every card is weighted by the share of the set's value concentration it
carries, and the metric asks how likely one pack is to contain it.

WHAT IT MUST NEVER BE CALLED
----------------------------
It is NOT "the chance of pulling a chase card", NOT "the probability of a chase"
and NOT "the chance to hit the chase". **There is no discrete chase roster.**
Every card carries continuous significance, so the binary "hit a chase" event
does not exist to have a probability. A value of 0.4% does not mean a 0.4%
chance of anything. Copy asserting otherwise is a defect, and the test suite
fails the build on that wording.

PROBABILITY AUTHORITY, AND A PERMANENT TRAP
-------------------------------------------
    p_i = simulation_card_variant_pull_rates.modeled_probability

Two neighbouring columns are NOT substitutes, and both have already caused a
silent, plausible, wrong answer once:

* ``effective_pull_rate`` is 1-in-N **odds** (observed 20-1430), not a
  probability. ``p_i = 1 / effective_pull_rate_i``. Passing it directly inverts
  the weighting - the rarest cards would dominate instead of the most
  significant ones.
* ``pull_count / simulation_count`` is expected **copies**, not P(N>=1). It
  differs from the presence probability on 2,398 of 7,615 cohort rows, because a
  pack can hold more than one copy of the same variant.

:func:`assert_probability_authority` and the permanent tests exist so neither
can be reintroduced.

NO SEALED-PRODUCT INPUT
-----------------------
Chase Accessibility is a SET-level access metric. It reads no product market
cost, no product identity and no pack count, and its public API physically
cannot accept them - :func:`compute_chase_accessibility` is keyword-only, which
a signature test pins.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

#: The published model identity. Stored on every row so a value can never be
#: read without the model that produced it.
CHASE_ACCESSIBILITY_VERSION = "chase_accessibility_v1_hc_value_squared_modeled_probability"

#: The weighting identity. Persisted as lineage; Chase Significance is not
#: itself published per card in V1.
CHASE_SIGNIFICANCE_VERSION = "chase_significance_v1_squared_value_share"

#: The companion depth identity.
CHASE_DEPTH_VERSION = "chase_depth_v1_hc_effective_count"

#: Minimum share of Chase Significance that must carry BOTH a finite positive
#: value and a valid modeled probability. Ratified by Stage XIV against observed
#: coverage: the worst real unmapped mass across the 22 supported sets is 0.0025,
#: so 0.99 leaves roughly 4x headroom while still refusing a set that has lost a
#: genuinely significant card.
MIN_MAPPED_HC_MASS = 0.99

STATUS_READY = "ready"
STATUS_NO_PULL_MODEL = "unavailable_pull_model"
STATUS_LOW_COVERAGE = "chase_accessibility_insufficient_probability_coverage"
STATUS_NO_UNIVERSE = "unavailable_no_drawable_universe"
STATUS_NO_PRICED_UNIVERSE = "unavailable_no_priced_universe"

#: Reason strings kept beside the statuses so a reader is never handed a bare
#: enum it has to interpret.
STATUS_REASONS: Dict[str, str] = {
    STATUS_NO_PULL_MODEL: (
        "this set has no authoritative modeled pull probabilities, so Accessibility "
        "cannot be computed. A pull rate is never fabricated and the metric is never "
        "extended to eras the pull model does not cover."),
    STATUS_LOW_COVERAGE: (
        "too much of this set's Chase Significance carries no value or no modeled "
        "probability. Unmapped significance is never renormalised away."),
    STATUS_NO_UNIVERSE: "no drawable card variants were supplied for this set.",
    STATUS_NO_PRICED_UNIVERSE: (
        "no drawable card variant carries a finite positive market value, so there is "
        "no value concentration to weight."),
}


class ChaseAccessibilityInputError(ValueError):
    """Raised when the inputs cannot describe one coherent set snapshot.

    Deliberately an exception rather than an ``unavailable`` status: a mixed set,
    a mixed calculation run or a duplicated variant is a CALLER defect, not a
    property of the set, and silently publishing ``unavailable`` would hide it.
    """


# --------------------------------------------------------------------------
# Coercion - strict, never silently forgiving
# --------------------------------------------------------------------------

def _finite(value: Any) -> Optional[float]:
    """A finite float, or None. NaN and the infinities are never values."""
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


def _valid_probability(value: Any) -> Optional[float]:
    """A probability in [0, 1].

    A value outside that interval is refused rather than clamped. Clamping is how
    an odds column gets silently accepted: an ``effective_pull_rate`` of 430
    would become 1.0 and the set would publish as perfectly accessible.
    """
    number = _finite(value)
    if number is None or number < 0.0 or number > 1.0:
        return None
    return number


# --------------------------------------------------------------------------
# Pure math
# --------------------------------------------------------------------------

def compute_chase_significance(values: Sequence[Any]) -> List[float]:
    """``HC_i = V_i^2 / sum_j V_j^2``.

    Sums to exactly 1 over a non-degenerate universe and is invariant to a
    uniform rescale of every price, because the scale cancels between numerator
    and denominator. Non-positive and non-finite values contribute 0.
    """
    squares = []
    for value in values:
        price = _finite_positive(value)
        squares.append(0.0 if price is None else price * price)
    total = math.fsum(squares)
    if total <= 0.0:
        return [0.0] * len(squares)
    return [square / total for square in squares]


def compute_chase_depth(significance: Sequence[float]) -> Optional[float]:
    """``N_HC = 1 / sum_i HC_i^2`` - the EFFECTIVE number of cards carrying the
    set's value concentration.

    A continuous quantity. It is never rounded into a card count, and there is no
    Core/Extended tier behind it: 3.9 does not mean "about four chase cards", it
    means the concentration is as top-heavy as 3.9 equally-important cards would be.
    """
    total = math.fsum(weight * weight for weight in significance)
    return None if total <= 0.0 else 1.0 / total


def compute_mapped_hc_mass(values: Sequence[Any], usable: Sequence[bool]) -> float:
    """Share of Chase Significance carrying both a value and a probability.

    Measured over the FULL drawable priced universe, INCLUDING the unusable
    cards. Dividing only by the usable cards' squares would renormalise the gap
    away and make a set look *more* accessible precisely because an important
    card went missing - which is the failure mode the 0.99 gate exists to catch.
    """
    squares = []
    for value in values:
        price = _finite_positive(value)
        squares.append(0.0 if price is None else price * price)
    total = math.fsum(squares)
    if total <= 0.0:
        return 0.0
    mapped = math.fsum(square for square, ok in zip(squares, usable) if ok)
    return mapped / total


def _accessibility_via_hc(significance: Sequence[float],
                          probabilities: Sequence[float]) -> float:
    return math.fsum(w * p for w, p in zip(significance, probabilities))


def _accessibility_direct(values: Sequence[float],
                          probabilities: Sequence[float]) -> float:
    squares = [value * value for value in values]
    total = math.fsum(squares)
    if total <= 0.0:
        return 0.0
    return math.fsum(square * p for square, p in zip(squares, probabilities)) / total


# --------------------------------------------------------------------------
# Probability authority
# --------------------------------------------------------------------------

def assert_probability_authority(rows: Iterable[Mapping[str, Any]], *,
                                 tolerance: float = 1e-6) -> Dict[str, Any]:
    """Check the two identities that make ``modeled_probability`` authoritative.

        modeled_probability ~= pack_presence_count / simulation_count
        modeled_probability ~= 1 / effective_pull_rate

    Reported, never enforced silently: a row failing either identity is counted
    and named so a data regression surfaces instead of being averaged away.
    """
    presence_checked = presence_failed = 0
    odds_checked = odds_failed = 0
    copies_differ = 0
    failures: List[Dict[str, Any]] = []

    for row in rows:
        probability = _valid_probability(row.get("modeled_probability"))
        if probability is None:
            continue
        simulations = _finite_positive(row.get("simulation_count"))
        presence = _finite(row.get("pack_presence_count"))
        if simulations and presence is not None:
            presence_checked += 1
            if abs(probability - presence / simulations) > tolerance:
                presence_failed += 1
                failures.append({"cardVariantId": row.get("card_variant_id"),
                                 "check": "pack_presence_count/simulation_count",
                                 "expected": presence / simulations,
                                 "observed": probability})
        odds = _finite_positive(row.get("effective_pull_rate"))
        if odds:
            odds_checked += 1
            if abs(probability - 1.0 / odds) > tolerance:
                odds_failed += 1
                failures.append({"cardVariantId": row.get("card_variant_id"),
                                 "check": "1/effective_pull_rate",
                                 "expected": 1.0 / odds, "observed": probability})
        pulls = _finite(row.get("pull_count"))
        if simulations and pulls is not None:
            if abs(probability - pulls / simulations) > tolerance:
                copies_differ += 1

    return {
        "presenceChecked": presence_checked, "presenceFailed": presence_failed,
        "oddsChecked": odds_checked, "oddsFailed": odds_failed,
        # NOT a failure. pull_count/simulation_count is expected COPIES; that it
        # differs from the presence probability is the reason it may never be
        # substituted for it.
        "rowsWhereExpectedCopiesDiffer": copies_differ,
        "failures": failures[:20],
        "holds": presence_failed == 0 and odds_failed == 0,
    }


# --------------------------------------------------------------------------
# The published computation
# --------------------------------------------------------------------------

def _unavailable(status: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "accessibility": None,
        "accessibilityPct": None,
        "chaseDepth": None,
        "status": status,
        "statusReason": STATUS_REASONS.get(status, ""),
        "publishable": False,
        "version": CHASE_ACCESSIBILITY_VERSION,
        "significanceVersion": CHASE_SIGNIFICANCE_VERSION,
        "depthVersion": CHASE_DEPTH_VERSION,
        "minMappedHcMass": MIN_MAPPED_HC_MASS,
    }
    payload.update(extra)
    return payload


def compute_chase_accessibility(
    *,
    variants: Sequence[Mapping[str, Any]],
    has_pull_model: bool = True,
    set_id: Optional[str] = None,
    calculation_run_id: Optional[str] = None,
    min_mapped_mass: float = MIN_MAPPED_HC_MASS,
) -> Dict[str, Any]:
    """Chase Accessibility for ONE set at ONE coherent calculation snapshot.

    ``variants`` are the drawable ``simulation_card_variant_pull_rates`` rows for
    that run: value and probability come from the SAME row, 1:1, with no
    canonical-card fan-out, no cross-table join and no product input.

    Keyword-only by design. There is no positional path and no ``**kwargs``, so a
    caller cannot smuggle a product cost or a pack count in; a signature test
    pins that.
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
        raise ChaseAccessibilityInputError(
            "Chase Accessibility spans one set; received %d: %s"
            % (len(set_ids), sorted(set_ids)[:5]))
    run_ids = {str(row.get("calculation_run_id")) for row in variants
               if row.get("calculation_run_id") is not None}
    if len(run_ids) > 1:
        raise ChaseAccessibilityInputError(
            "Chase Accessibility describes one calculation run; received %d: %s"
            % (len(run_ids), sorted(run_ids)[:5]))
    if calculation_run_id is not None and run_ids and str(calculation_run_id) not in run_ids:
        raise ChaseAccessibilityInputError(
            "rows belong to run %s, not the requested %s"
            % (sorted(run_ids)[0], calculation_run_id))

    identities = [row.get("card_variant_id") for row in variants]
    if any(identity is None for identity in identities):
        raise ChaseAccessibilityInputError("every row needs a card_variant_id")
    if len({str(identity) for identity in identities}) != len(identities):
        raise ChaseAccessibilityInputError(
            "duplicate card_variant_id rows: Chase Significance would double-count them")

    # ---- the full drawable priced universe ---------------------------------
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
    total_squared = math.fsum(
        (_finite_positive(value) or 0.0) ** 2 for value in values)

    diagnostics = {
        "setId": set_id,
        "calculationRunId": calculation_run_id or (sorted(run_ids)[0] if run_ids else None),
        "eligibleVariantCount": len(variants),
        "pricedVariantCount": priced_count,
        "probabilityMappedVariantCount": sum(usable),
        "totalSquaredValue": total_squared,
        "mappedHcMass": mapped_mass,
        "minMappedHcMass": min_mapped_mass,
    }

    if mapped_mass < min_mapped_mass:
        return _unavailable(STATUS_LOW_COVERAGE, unmappedHcMass=1.0 - mapped_mass,
                            **diagnostics)

    usable_values = [float(_finite_positive(values[i]))
                     for i in range(len(variants)) if usable[i]]
    usable_probabilities = [float(probabilities[i])
                            for i in range(len(variants)) if usable[i]]

    significance = compute_chase_significance(usable_values)
    via_hc = _accessibility_via_hc(significance, usable_probabilities)
    direct = _accessibility_direct(usable_values, usable_probabilities)
    depth = compute_chase_depth(significance)

    ordered = sorted(range(len(significance)), key=lambda i: -significance[i])
    top = ordered[0] if ordered else None

    return {
        "accessibility": via_hc,
        # Presentation multiplies the canonical decimal fraction by 100. The
        # fraction is the stored value; the percentage is a convenience.
        "accessibilityPct": via_hc * 100.0,
        "parityDelta": abs(via_hc - direct),
        "chaseDepth": depth,
        "hcTop1": significance[top] if top is not None else None,
        "accessibilityShareTop1": (
            significance[top] * usable_probabilities[top] / via_hc
            if top is not None and via_hc > 0 else None),
        "status": STATUS_READY,
        "statusReason": None,
        "publishable": True,
        "version": CHASE_ACCESSIBILITY_VERSION,
        "significanceVersion": CHASE_SIGNIFICANCE_VERSION,
        "depthVersion": CHASE_DEPTH_VERSION,
        **diagnostics,
    }
