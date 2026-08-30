"""Stage-II chase measures: Chase EV, Beat-the-Buy, and the Chase Cost Gap.

THREE DIFFERENT QUESTIONS, KEPT APART ON PURPOSE
------------------------------------------------
Stage I failed because one number was asked to be both an expected-value
statement and an efficiency statement. These are deliberately separate:

* ``Chase EV``      - "how much of a pack's expected value comes specifically
                      from cards I would call chases?" This IS an EV metric and
                      is labelled as one. It is not evidence of efficiency.
* ``Beat-the-Buy``  - "how often does ripping reach a chase before I have spent
                      more than that chase costs to buy?" This is a probability,
                      bounded in [0,1], and is the actual efficiency candidate.
* ``Chase Cost Gap``- "how much more (or less) did the chase cost me by ripping
                      than by buying it?" A dollar distribution, not a score.

WHY BEAT-THE-BUY CANNOT DEGENERATE THE WAY STAGE I's METRIC DID
---------------------------------------------------------------
Stage I's collapse came from ``V_S * p_S = E_S``: the conditional mean times the
probability reconstructed an unconditional expectation, so the hazard term
turned basket expansion into a free win. Beat-the-Buy has no such identity. It
is an expectation of a BOUNDED, CONCAVE function of ``Y``,

    E_Y[ 1 - (1 - p_S)^floor(Y / C) ]

and the ``floor(Y/C)`` exponent is exactly zero for any card worth less than one
pack. Adding cheap cards therefore drags the ``Y`` distribution down toward
terms that contribute ZERO while still raising ``p_S``, so the two effects fight
each other instead of compounding. Whether that fight produces an interior
optimum in practice is an empirical question this module exists to answer, not
an assumption it makes.

THE INDEPENDENCE ASSUMPTION, AND HOW IT IS CHECKED
--------------------------------------------------
The closed form requires ``T`` (packs to first chase) to be independent of ``Y``
(value of the chase obtained). That holds under the pipeline's documented
``packIndependenceAssumption`` - packs are i.i.d. draws - because the content of
the first successful pack cannot depend on how many failures preceded it. This
module does NOT take that on trust: ``beat_the_buy`` computes the closed form
AND walks the recorded pack sequence as an actual repeated-opening journey, and
the two are reported side by side with their sampling error.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

PRECISION = 12


def _finite_positive(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def chase_ev(
    *,
    qualifying_totals: np.ndarray,
    pack_cost: Optional[float],
    full_pack_values: np.ndarray,
) -> Dict[str, Any]:
    """Expected per-pack value from the chase universe alone.

    Every non-qualifying card is worth exactly $0 here. That is the definition,
    not an approximation: the question is what the chase pool contributes, and
    crediting a $0.20 common against it would answer a different one.

    ``chaseEvShareOfTotalEv`` is the diagnostic that matters most - it separates
    sets whose value is essentially all chase from sets carried by a long tail
    of mid-tier cards.
    """
    totals = np.asarray(qualifying_totals, dtype=np.float64)
    packs = int(totals.size)
    if packs == 0:
        return {"packs": 0, "chaseEv": None, "chaseEvReturn": None,
                "fullPackEv": None, "chaseEvShareOfTotalEv": None,
                "nonChaseEv": None, "nonChaseEvShareOfTotalEv": None}
    value = float(totals.mean())
    full = float(np.asarray(full_pack_values, dtype=np.float64).mean())
    cost = _finite_positive(pack_cost)
    return {
        "packs": packs,
        "chaseEv": round(value, PRECISION),
        "chaseEvReturn": None if cost is None else round(value / cost, PRECISION),
        "fullPackEv": round(full, PRECISION),
        "fullPackEvReturn": None if cost is None else round(full / cost, PRECISION),
        "chaseEvShareOfTotalEv": round(value / full, PRECISION) if full > 0 else None,
        "nonChaseEv": round(full - value, PRECISION),
        "nonChaseEvShareOfTotalEv": (round((full - value) / full, PRECISION)
                                     if full > 0 else None),
    }


def chase_journeys(qualifying: np.ndarray, values: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Walk the recorded pack sequence as repeated chase attempts.

    Returns ``(T, Y)``: packs opened to reach each first chase, and the value
    obtained from that successful pack. Each success ENDS a journey and the next
    pack starts a fresh one, so no pack is counted in two journeys and a
    multi-chase pack is one success, not several.

    This is the direct-simulation answer. It makes no independence assumption
    because it never separates ``T`` from ``Y`` - it observes the pair.
    """
    hits = np.flatnonzero(np.asarray(qualifying, dtype=bool))
    if hits.size == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64)
    packs_used = np.diff(np.concatenate(([-1], hits))).astype(np.int64)
    return packs_used, np.asarray(values, dtype=np.float64)[hits]


def beat_the_buy(
    *,
    qualifying: np.ndarray,
    chase_values: np.ndarray,
    probability: Optional[float],
    pack_cost: Optional[float],
) -> Dict[str, Any]:
    """P(cumulative opening spend to the first chase <= value of that chase).

    Two independent estimates:

    * ``closedForm`` - ``E_Y[1 - (1-p)^floor(Y/C)]`` over the observed
      conditional distribution of ``Y``. Marginalises ``T`` analytically and so
      relies on ``T`` being independent of ``Y``.
    * ``direct`` - the fraction of actually-walked journeys satisfying
      ``C * T <= Y``. Assumes nothing.

    Agreement between the two IS the validation of the independence assumption,
    so both are always returned rather than one being chosen.

    ``floor(Y / C)`` is the number of packs whose combined cost the chase would
    still cover. It is zero for any chase worth less than a single pack, which
    correctly makes such a card unable to contribute to beating the buy.
    """
    cost = _finite_positive(pack_cost)
    p = _finite_positive(probability)
    mask = np.asarray(qualifying, dtype=bool)
    successes = int(np.count_nonzero(mask))
    if cost is None or p is None or p > 1.0 or successes == 0:
        return {
            "closedForm": None, "direct": None, "agreementAbsolute": None,
            "journeys": 0, "successfulPacks": successes,
            "reason": ("no qualifying chase observed" if successes == 0
                       else "unusable pack cost or probability"),
        }

    conditional_y = np.asarray(chase_values, dtype=np.float64)[mask]
    affordable_packs = np.floor(conditional_y / cost)
    closed = float(np.mean(1.0 - np.power(1.0 - p, affordable_packs)))

    packs_used, obtained = chase_journeys(mask, chase_values)
    direct = float(np.mean(cost * packs_used <= obtained)) if packs_used.size else None

    standard_error = None
    if direct is not None and packs_used.size:
        standard_error = math.sqrt(max(direct * (1.0 - direct), 0.0) / packs_used.size)

    return {
        "closedForm": round(closed, PRECISION),
        "direct": None if direct is None else round(direct, PRECISION),
        "directStandardError": None if standard_error is None else round(standard_error, PRECISION),
        "agreementAbsolute": (None if direct is None
                              else round(abs(closed - direct), PRECISION)),
        "journeys": int(packs_used.size),
        "successfulPacks": successes,
        "medianAffordablePacks": float(np.median(affordable_packs)),
        "shareOfChasesWorthLessThanOnePack": round(
            float(np.mean(affordable_packs < 1.0)), PRECISION),
        "reason": None,
    }


def chase_cost_gap(
    *,
    qualifying: np.ndarray,
    chase_values: np.ndarray,
    pack_cost: Optional[float],
) -> Dict[str, Any]:
    """Distribution of ``C * T - Y`` over walked chase journeys.

    NOT a profit-and-loss figure, and deliberately not named like one: every
    non-chase card pulled along the way is credited at $0, so this overstates
    what the journey really costs someone who sells the rest. It answers only
    "what did reaching this chase cost me, against buying that same chase".

    Negative is ripping winning; positive is buying winning.
    """
    cost = _finite_positive(pack_cost)
    packs_used, obtained = chase_journeys(np.asarray(qualifying, dtype=bool), chase_values)
    if cost is None or packs_used.size == 0:
        return {"journeys": 0, "reason": ("no qualifying chase observed"
                                          if packs_used.size == 0 else "unusable pack cost")}
    spend = cost * packs_used
    gap = spend - obtained
    return {
        "journeys": int(packs_used.size),
        "meanGap": round(float(gap.mean()), PRECISION),
        "medianGap": round(float(np.median(gap)), PRECISION),
        "p25Gap": round(float(np.percentile(gap, 25)), PRECISION),
        "p75Gap": round(float(np.percentile(gap, 75)), PRECISION),
        "p90Gap": round(float(np.percentile(gap, 90)), PRECISION),
        "probabilityGapAtMostZero": round(float(np.mean(gap <= 0.0)), PRECISION),
        "probabilityGapWithin25PercentOfValue": round(
            float(np.mean(gap <= 0.25 * obtained)), PRECISION),
        "probabilityGapExceedsValue": round(float(np.mean(gap > obtained)), PRECISION),
        "meanSpendToFirstChase": round(float(spend.mean()), PRECISION),
        "medianSpendToFirstChase": round(float(np.median(spend)), PRECISION),
        "meanChaseValueObtained": round(float(obtained.mean()), PRECISION),
        "medianChaseValueObtained": round(float(np.median(obtained)), PRECISION),
        "meanPacksToFirstChase": round(float(packs_used.mean()), PRECISION),
        "reason": None,
    }
