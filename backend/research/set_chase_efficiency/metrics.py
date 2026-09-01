"""Pure Set Chase Efficiency mathematics.

WHAT THIS MODULE IS FOR
-----------------------
    "If someone opens this set because they want ONE OF ITS meaningful chase
     cards, how economically favourable is that chase?"

The unit of analysis is a BASKET of qualifying chase cards, not a single card
and not an average over single cards. Averaging card-level Chase Efficiency is
explicitly wrong here: CE is non-linear in ``p`` and the per-card hit events
inside one pack are neither independent nor mutually exclusive, so a mean of
card scores answers no question anyone asked.

THE CANDIDATE FORM
------------------
    CE_set(S) = (V_S / C) * [-ln(1 - p_S)]

``-ln(1 - p)`` is the per-pack HAZARD: the exponential rate at which cumulative
chase probability accrues, so ``n`` packs reach ``1 - exp(-n * hazard)``. It is
the same hazard the card-level implementation
(``backend.domain.pokemon.chase_efficiency``) already uses, which is what makes
the two scales commensurable at all.

WHERE p_S COMES FROM, AND WHY NOT A CLOSED FORM
-----------------------------------------------
``p_S`` is NEVER assembled from per-card odds in this module. It arrives as an
observed per-pack indicator vector from the authoritative V2 simulator's own
sampled paths (``PackDecomposition``), so mutually exclusive pack states, the
without-replacement rule across variable slots, pattern overlays and both
special-pack entry paths are honoured exactly rather than assumed away. A
closed form built from ``simulation_input_cards.effective_pull_rate`` would be a
SECOND model of the simulator and would be wrong for baskets in particular,
where several members compete for the same slot.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence

import numpy as np

PRECISION = 12

#: Chase horizons reported for every basket. Ordered ascending; the frontier's
#: monotonicity check depends on that order.
CHASE_HORIZONS = (0.50, 0.75, 0.80, 0.90)


def finite_positive(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def valid_probability(value: Any) -> Optional[float]:
    """A usable ``p_S``: strictly positive and at most 1.

    ``p_S == 0`` is NOT coerced to a score. An unreachable basket has no chase
    to be efficient at, and returning 0.0 would rank it beside a reachable but
    worthless one.
    """
    number = finite_positive(value)
    return number if number is not None and number <= 1.0 else None


def hazard(probability: Any) -> Optional[float]:
    """``-ln(1 - p)``, stable for very small ``p`` via ``log1p``.

    ``p == 1`` has infinite hazard and therefore infinite CE. That is
    mathematically correct and economically meaningless, so it is refused
    rather than stored as a number that would top every ranking.
    """
    p = valid_probability(probability)
    if p is None or p >= 1.0:
        return None
    return -math.log1p(-p)


def chase_efficiency(*, conditional_value: Any, pack_cost: Any, probability: Any) -> Optional[float]:
    """``(V_S / C) * hazard(p_S)``. ``None`` whenever any input is unusable."""
    value = finite_positive(conditional_value)
    cost = finite_positive(pack_cost)
    rate = hazard(probability)
    if value is None or cost is None or rate is None:
        return None
    result = (value / cost) * rate
    return round(result, PRECISION) if math.isfinite(result) else None


def packs_for_horizon(probability: Any, horizon: float) -> Optional[float]:
    """Mathematical (fractional) packs to reach cumulative ``horizon``.

    ``n_q = ln(1 - q) / ln(1 - p)``. Reported beside the discrete count because
    the two answer different questions: the fractional value is the metric's
    own scale, the integer is what a person actually buys.
    """
    rate = hazard(probability)
    if rate is None or not 0.0 < horizon < 1.0:
        return None
    return round(-math.log1p(-horizon) / rate, PRECISION)


def whole_packs_for_horizon(probability: Any, horizon: float) -> Optional[int]:
    """First WHOLE pack count whose cumulative probability reaches ``horizon``.

    Computed by ceiling the exact value and then verifying, because floating
    point at the boundary can otherwise return a count one short of the target.
    """
    exact = packs_for_horizon(probability, horizon)
    if exact is None:
        return None
    p = float(valid_probability(probability))
    n = max(1, int(math.ceil(exact)))
    while n > 1 and 1.0 - (1.0 - p) ** (n - 1) >= horizon:
        n -= 1
    while 1.0 - (1.0 - p) ** n < horizon:
        n += 1
    return n


def _percentile(sorted_values: np.ndarray, q: float) -> float:
    return float(np.percentile(sorted_values, q))


def conditional_value_statistics(values: np.ndarray, *, winsor: float = 0.05,
                                 trim: float = 0.10) -> Dict[str, Any]:
    """Every candidate ``V_S`` over the openings that actually qualified.

    ``values`` must ALREADY be conditioned on a qualifying hit: passing the
    zeros of the non-qualifying packs would silently answer a different
    question (unconditional expected chase value, which is just EV again).

    Both a winsorized and a trimmed mean are produced because chase baskets are
    exactly where extreme-card skew is expected, and the study needs to show
    whether the choice moves rankings rather than assert that it does not.
    """
    observations = np.asarray(values, dtype=np.float64)
    count = int(observations.size)
    if count == 0:
        return {
            "count": 0, "mean": None, "median": None, "winsorizedMean": None,
            "trimmedMean": None, "min": None, "max": None, "p25": None,
            "p75": None, "p95": None, "p99": None, "std": None,
            "winsorLevel": winsor, "trimLevel": trim,
        }
    ordered = np.sort(observations)
    low = _percentile(ordered, winsor * 100.0)
    high = _percentile(ordered, (1.0 - winsor) * 100.0)
    winsorized = np.clip(ordered, low, high)
    cut = int(math.floor(count * trim))
    trimmed = ordered[cut: count - cut] if count - 2 * cut > 0 else ordered
    return {
        "count": count,
        "mean": round(float(ordered.mean()), PRECISION),
        "median": round(float(np.median(ordered)), PRECISION),
        "winsorizedMean": round(float(winsorized.mean()), PRECISION),
        "trimmedMean": round(float(trimmed.mean()), PRECISION),
        "min": round(float(ordered[0]), PRECISION),
        "max": round(float(ordered[-1]), PRECISION),
        "p25": round(_percentile(ordered, 25.0), PRECISION),
        "p75": round(_percentile(ordered, 75.0), PRECISION),
        "p95": round(_percentile(ordered, 95.0), PRECISION),
        "p99": round(_percentile(ordered, 99.0), PRECISION),
        "std": round(float(ordered.std(ddof=0)), PRECISION),
        "winsorLevel": winsor,
        "trimLevel": trim,
    }


def hit_count_distribution(counts: np.ndarray) -> Dict[str, Any]:
    """P(0), P(1), P(>=2) and the identity check ``P(>=1) == 1 - P(0)``.

    The identity is VERIFIED rather than assumed: it is the cheapest available
    proof that the presence vector and the count vector were derived from the
    same sampled paths.
    """
    observations = np.asarray(counts)
    packs = int(observations.size)
    if packs == 0:
        return {"packs": 0, "pZero": None, "pExactlyOne": None, "pTwoOrMore": None,
                "pAtLeastOne": None, "identityHolds": False,
                "expectedQualifyingCopiesPerPack": None, "maxQualifyingInOnePack": None}
    zero = int(np.count_nonzero(observations == 0))
    one = int(np.count_nonzero(observations == 1))
    two_plus = packs - zero - one
    p_zero = zero / packs
    p_at_least_one = (packs - zero) / packs
    return {
        "packs": packs,
        "pZero": round(p_zero, PRECISION),
        "pExactlyOne": round(one / packs, PRECISION),
        "pTwoOrMore": round(two_plus / packs, PRECISION),
        "pAtLeastOne": round(p_at_least_one, PRECISION),
        "identityHolds": abs(p_at_least_one - (1.0 - p_zero)) < 1e-12,
        "expectedQualifyingCopiesPerPack": round(float(observations.sum()) / packs, PRECISION),
        "maxQualifyingInOnePack": int(observations.max()),
    }


def binomial_standard_error(p: Optional[float], packs: int) -> Optional[float]:
    """Monte Carlo sampling error on ``p_S``.

    Published beside every ``p_S`` so a reader can tell a real ranking gap from
    simulation noise. A Top-1 basket on a 1-in-1500 card is the case where this
    matters and where an unreported figure would mislead.
    """
    if p is None or packs <= 0:
        return None
    return round(math.sqrt(max(p * (1.0 - p), 0.0) / packs), PRECISION)


def concentration(contributions: Sequence[float]) -> Dict[str, Any]:
    """How much of a basket's chase VALUE comes from its biggest members.

    ``contributions`` is total qualifying value delivered per basket member
    across the whole run, so it already carries both how often a member is hit
    and what it is worth - which is the only combination that can distinguish a
    single-hero-chase set from a deep-chase one.
    """
    values = np.asarray([float(v) for v in contributions], dtype=np.float64)
    values = values[np.isfinite(values)]
    total = float(values.sum())
    if values.size == 0 or total <= 0.0:
        return {"members": int(values.size), "total": total, "top1Share": None,
                "top3Share": None, "top5Share": None, "remainderShare": None,
                "herfindahl": None, "effectiveChaseCount": None}
    ordered = np.sort(values)[::-1]
    shares = ordered / total

    def head(k: int) -> float:
        return round(float(shares[:k].sum()), PRECISION)

    hhi = float((shares ** 2).sum())
    return {
        "members": int(values.size),
        "total": round(total, PRECISION),
        "top1Share": head(1),
        "top3Share": head(3),
        "top5Share": head(5),
        "remainderShare": round(float(shares[5:].sum()), PRECISION),
        "herfindahl": round(hhi, PRECISION),
        "effectiveChaseCount": round(1.0 / hhi, PRECISION) if hhi > 0 else None,
    }


def horizon_block(probability: Any, pack_cost: Any) -> Dict[str, Any]:
    """Chase horizons and the spend each one implies."""
    cost = finite_positive(pack_cost)
    block: Dict[str, Any] = {}
    for q in CHASE_HORIZONS:
        key = str(int(round(q * 100)))
        exact = packs_for_horizon(probability, q)
        whole = whole_packs_for_horizon(probability, q)
        block[key] = {
            "packsExact": exact,
            "packsWhole": whole,
            "spendExact": None if exact is None or cost is None else round(exact * cost, PRECISION),
            "spendWhole": None if whole is None or cost is None else round(whole * cost, PRECISION),
        }
    return block
