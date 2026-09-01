"""Phase 5: four ways of asking how much of the score Chase actually is.

RESEARCH ONLY.

WHY FOUR METHODS AND NO WINNER
------------------------------
The three pillars are correlated (Chase Opportunity and Financial RIP share a
rank correlation near +0.5), so "how much of the variance is Chase" has no
single correct answer, and the brief is explicit that none may be claimed as
uniquely correct. Four are reported side by side:

* :func:`direct_variance` - ``w^2 var_i / var_total``. Ignores covariance, so
  the shares do NOT sum to one. Honest about being incomplete.
* :func:`covariance_share` - ``cov(w_i x_i, total) / var_total``. Sums to
  exactly one by construction, and assigns each pillar its covariance with the
  whole. This is the Stage VI number, kept for continuity.
* :func:`drop_one_share` - the variance that disappears when the pillar is
  removed and the score renormalized. Answers "what would we lose", which is
  the question a weight decision actually faces.
* :func:`shapley_shares` - the exact Shapley value over the three players,
  enumerated over all eight coalitions. The only one of the four that is
  symmetric, efficient and covariance-aware simultaneously.

When the four disagree the disagreement is the finding, and the report prints
them together rather than picking one.
"""

from __future__ import annotations

import itertools
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np


def _weighted(components: Mapping[str, Sequence[float]],
              weights: Mapping[str, float]) -> Dict[str, np.ndarray]:
    return {name: np.asarray([float(v) for v in values], dtype=np.float64)
            * float(weights.get(name, 0.0))
            for name, values in components.items()}


def _variance(array: np.ndarray) -> float:
    return float(np.var(array, ddof=1)) if array.size > 1 else 0.0


def direct_variance(components, weights) -> Dict[str, Optional[float]]:
    """Own-variance only. Shares are not expected to sum to one."""
    weighted = _weighted(components, weights)
    total = _variance(sum(weighted.values()))
    return {name: (_variance(column) / total if total else None)
            for name, column in weighted.items()}


def covariance_share(components, weights) -> Dict[str, Optional[float]]:
    """Covariance-with-the-total decomposition. Sums to exactly one."""
    weighted = _weighted(components, weights)
    total = sum(weighted.values())
    variance = _variance(total)
    if not variance:
        return {name: None for name in weighted}
    return {name: float(np.cov(column, total, ddof=1)[0, 1]) / variance
            for name, column in weighted.items()}


def drop_one_share(components, weights) -> Dict[str, Optional[float]]:
    """Variance lost when a pillar is dropped and the rest renormalized.

    Renormalizing matters: dropping a pillar and leaving the others at their old
    weights would shrink the composite's scale and report a loss that is mostly
    arithmetic. The remaining weights are rescaled to sum to one first, so what
    is measured is the loss of the pillar's INFORMATION, not of its magnitude.
    """
    weighted = _weighted(components, weights)
    total_variance = _variance(sum(weighted.values()))
    if not total_variance:
        return {name: None for name in weighted}
    out: Dict[str, Optional[float]] = {}
    for dropped in weighted:
        remaining = {n: float(weights.get(n, 0.0)) for n in weighted if n != dropped}
        scale = sum(remaining.values())
        if scale <= 0:
            out[dropped] = None
            continue
        rescaled = sum(np.asarray([float(v) for v in components[n]], dtype=np.float64)
                       * (w / scale) for n, w in remaining.items())
        out[dropped] = 1.0 - _variance(rescaled) / total_variance
    return out


def shapley_shares(components, weights) -> Dict[str, Optional[float]]:
    """Exact Shapley value of each pillar's contribution to composite variance.

    The characteristic function of a coalition is the variance of the weighted
    sum of its members. Three players, eight coalitions, enumerated exactly - no
    sampling, so there is no Monte Carlo error to argue about. Shares sum to the
    total variance and are renormalized to fractions.
    """
    names = list(components)
    weighted = _weighted(components, weights)
    zero = np.zeros(len(next(iter(weighted.values()))), dtype=np.float64)

    def value(coalition) -> float:
        if not coalition:
            return 0.0
        return _variance(sum((weighted[n] for n in coalition), zero))

    total = value(names)
    if not total:
        return {name: None for name in names}

    count = len(names)
    factorial = [1]
    for i in range(1, count + 1):
        factorial.append(factorial[-1] * i)

    shares: Dict[str, Optional[float]] = {}
    for player in names:
        others = [n for n in names if n != player]
        accumulated = 0.0
        for size in range(len(others) + 1):
            weight = (factorial[size] * factorial[count - size - 1]) / factorial[count]
            for coalition in itertools.combinations(others, size):
                accumulated += weight * (value(list(coalition) + [player])
                                         - value(list(coalition)))
        shares[player] = accumulated / total
    return shares


METHODS = {
    "direct": direct_variance,
    "covariance": covariance_share,
    "dropOne": drop_one_share,
    "shapley": shapley_shares,
}


def attribute(components: Mapping[str, Sequence[float]],
              weights: Mapping[str, float]) -> Dict[str, Any]:
    """All four methods, plus the leverage ratio each one implies for Chase."""
    nominal = float(weights.get("chase", 0.0))
    results = {name: method(components, weights) for name, method in METHODS.items()}
    leverage = {
        name: (None if result.get("chase") is None or nominal <= 0
               else result["chase"] / nominal)
        for name, result in results.items()
    }
    return {
        "nominalChaseWeight": nominal,
        "shares": results,
        "chaseLeverage": leverage,
        "covarianceSumsToOne": (
            None if any(v is None for v in results["covariance"].values())
            else sum(results["covariance"].values())),
        "shapleySumsToOne": (
            None if any(v is None for v in results["shapley"].values())
            else sum(results["shapley"].values())),
    }
