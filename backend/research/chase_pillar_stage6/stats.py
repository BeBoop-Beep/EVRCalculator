"""Statistical apparatus for the Stage VI third-pillar study.

RESEARCH ONLY. Nothing here is read by production.

Everything in this module is deliberately small and explicit rather than
delegated to a modelling library, because the study's conclusions turn on
knowing exactly what was fitted. In particular:

* :func:`reconstruct` always reports an **adjusted** and a **cross-validated**
  R2 alongside the in-sample one. With n = 131 products and up to a dozen
  predictors, in-sample R2 alone would flatter every model and would make the
  Phase-7 and Phase-15 redundancy gates unfalsifiable.
* :func:`cross_validated_r2` folds by **set**, not by row. Products of one set
  share a card universe and a simulated pack path, so a random row split would
  leak a set's chase structure between train and test and inflate the apparent
  reconstructability of every Chase candidate. Grouped folds are the honest
  version of the question "could the existing pillars have told me this about a
  product I have not seen?".
* :func:`partial_correlation` is computed by residualising both sides on the
  controls, which is the definition, so a partial correlation and a
  reconstruction residual are talking about the same object.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

#: Stage VI redundancy language, fixed here so no report can quietly move the
#: bar. These are diagnostics, not automatic verdicts.
STRONG_REDUNDANCY = 0.85
MODERATE_OVERLAP = 0.65


def _clean_pair(x: Sequence[Any], y: Sequence[Any]) -> Tuple[np.ndarray, np.ndarray]:
    pairs = [(float(a), float(b)) for a, b in zip(x, y)
             if a is not None and b is not None
             and not (isinstance(a, float) and math.isnan(a))
             and not (isinstance(b, float) and math.isnan(b))]
    if not pairs:
        return np.zeros(0), np.zeros(0)
    array = np.asarray(pairs, dtype=np.float64)
    return array[:, 0], array[:, 1]


def pearson(x: Sequence[Any], y: Sequence[Any]) -> Optional[float]:
    a, b = _clean_pair(x, y)
    if a.size < 3 or a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def rank(values: Sequence[float]) -> np.ndarray:
    """Average ranks for ties.

    Ties are the norm here - Core K is a small integer and many products share
    one - and competition ranking would fabricate agreement between two vectors
    that are mostly ties.
    """
    array = np.asarray(values, dtype=np.float64)
    order = np.argsort(array, kind="mergesort")
    out = np.empty(array.size, dtype=np.float64)
    position = 0
    while position < array.size:
        end = position
        while end + 1 < array.size and array[order[end + 1]] == array[order[position]]:
            end += 1
        out[order[position:end + 1]] = (position + end) / 2.0 + 1.0
        position = end + 1
    return out


def spearman(x: Sequence[Any], y: Sequence[Any]) -> Optional[float]:
    a, b = _clean_pair(x, y)
    if a.size < 3:
        return None
    ra, rb = rank(a), rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def kendall_tau(x: Sequence[Any], y: Sequence[Any]) -> Optional[float]:
    """Tau-b, so the tie-heavy Chase vectors are scored honestly."""
    a, b = _clean_pair(x, y)
    n = a.size
    if n < 3:
        return None
    concordant = discordant = tie_a = tie_b = 0
    for i in range(n - 1):
        da = a[i + 1:] - a[i]
        db = b[i + 1:] - b[i]
        product = da * db
        concordant += int(np.sum(product > 0))
        discordant += int(np.sum(product < 0))
        tie_a += int(np.sum((da == 0) & (db != 0)))
        tie_b += int(np.sum((db == 0) & (da != 0)))
        tie_a += int(np.sum((da == 0) & (db == 0)))
    denominator = math.sqrt((concordant + discordant + tie_a)
                            * (concordant + discordant + tie_b))
    return (concordant - discordant) / denominator if denominator else None


def classify_overlap(rho: Optional[float]) -> str:
    if rho is None:
        return "undefined"
    magnitude = abs(rho)
    if magnitude >= STRONG_REDUNDANCY:
        return "strong_redundancy"
    if magnitude >= MODERATE_OVERLAP:
        return "moderate_overlap"
    return "distinct"


# --------------------------------------------------------------------------
# Least squares with an intercept
# --------------------------------------------------------------------------

def _design(predictors: Sequence[Sequence[float]], rows: int) -> np.ndarray:
    columns = [np.ones(rows)]
    for column in predictors:
        columns.append(np.asarray(column, dtype=np.float64))
    return np.column_stack(columns)


def _fit(matrix: np.ndarray, target: np.ndarray) -> np.ndarray:
    coefficients, *_ = np.linalg.lstsq(matrix, target, rcond=None)
    return coefficients


def r_squared(actual: np.ndarray, predicted: np.ndarray) -> Optional[float]:
    total = float(np.sum((actual - actual.mean()) ** 2))
    if total <= 0:
        return None
    residual = float(np.sum((actual - predicted) ** 2))
    return 1.0 - residual / total


def cross_validated_r2(target: Sequence[float], predictors: Sequence[Sequence[float]],
                       groups: Sequence[Any]) -> Optional[float]:
    """Leave-one-GROUP-out R2, grouped by set.

    Out-of-sample R2 is computed against the FULL-sample mean, not each fold's
    own mean, so a fold cannot look good merely by being homogeneous. It can go
    negative, and a negative value is meaningful: the pillars predict that
    candidate worse than a constant does.
    """
    y = np.asarray(target, dtype=np.float64)
    if y.size < 6:
        return None
    matrix = _design(predictors, y.size)
    labels = [str(g) for g in groups]
    unique = sorted(set(labels))
    if len(unique) < 3:
        return None
    predictions = np.empty(y.size, dtype=np.float64)
    membership = np.asarray(labels)
    for held_out in unique:
        test = membership == held_out
        train = ~test
        if train.sum() <= matrix.shape[1]:
            return None
        coefficients = _fit(matrix[train], y[train])
        predictions[test] = matrix[test] @ coefficients
    return r_squared(y, predictions)


def reconstruct(*, name: str, target: Sequence[float],
                predictors: Mapping[str, Sequence[float]],
                groups: Sequence[Any]) -> Dict[str, Any]:
    """How well is ``target`` reconstructed from ``predictors``?

    The Stage VI question is not "is there a fit" but "is there anything LEFT".
    The residual block is therefore reported as prominently as the R2: a
    candidate with a high R2 but a large, structured residual can still be worth
    a pillar, and a candidate with a low R2 whose residual is pure noise is not.
    """
    y = np.asarray([float(v) for v in target], dtype=np.float64)
    columns = [np.asarray([float(v) for v in column], dtype=np.float64)
               for column in predictors.values()]
    matrix = _design(columns, y.size)
    coefficients = _fit(matrix, y)
    fitted = matrix @ coefficients
    residual = y - fitted
    r2 = r_squared(y, fitted)
    k = len(columns)
    adjusted = (None if r2 is None or y.size - k - 1 <= 0
                else 1.0 - (1.0 - r2) * (y.size - 1) / (y.size - k - 1))
    return {
        "name": name,
        "predictors": list(predictors),
        "n": int(y.size),
        "r2": r2,
        "adjustedR2": adjusted,
        "crossValidatedR2": cross_validated_r2(y, columns, groups),
        "residualStd": float(residual.std(ddof=1)) if y.size > 1 else None,
        "targetStd": float(y.std(ddof=1)) if y.size > 1 else None,
        "residualShareOfSd": (float(residual.std(ddof=1) / y.std(ddof=1))
                              if y.size > 1 and y.std(ddof=1) > 0 else None),
        "residuals": residual.tolist(),
        "fitted": fitted.tolist(),
    }


def residualise(target: Sequence[float],
                controls: Sequence[Sequence[float]]) -> np.ndarray:
    y = np.asarray([float(v) for v in target], dtype=np.float64)
    if not controls:
        return y - y.mean()
    matrix = _design([np.asarray([float(v) for v in c], dtype=np.float64)
                      for c in controls], y.size)
    return y - matrix @ _fit(matrix, y)


def partial_correlation(*, x: Sequence[float], y: Sequence[float],
                        controls: Mapping[str, Sequence[float]]) -> Dict[str, Any]:
    """Correlation of ``x`` and ``y`` once both are cleared of the controls.

    Both Pearson and Spearman forms are returned. They can disagree, and when
    they do it is informative: a partial Pearson near zero with a healthy
    partial Spearman means the residual relationship is monotone but not
    linear, which is exactly the shape a saturating structural metric produces.
    """
    control_columns = [list(v) for v in controls.values()]
    rx = residualise(x, control_columns)
    ry = residualise(y, control_columns)
    return {
        "controls": list(controls),
        "n": len(rx),
        "partialPearson": pearson(rx, ry),
        "partialSpearman": spearman(rx, ry),
        "rawPearson": pearson(x, y),
        "rawSpearman": spearman(x, y),
    }


# --------------------------------------------------------------------------
# Rank movement
# --------------------------------------------------------------------------

def rank_movement(baseline: Sequence[float], candidate: Sequence[float], *,
                  labels: Sequence[str], top_n: Sequence[int] = (5, 10)) -> Dict[str, Any]:
    """Movement of a candidate ranking against CONTROL. Rank 1 = best."""
    base = np.asarray([float(v) for v in baseline], dtype=np.float64)
    cand = np.asarray([float(v) for v in candidate], dtype=np.float64)
    base_rank = rank(-base)
    cand_rank = rank(-cand)
    delta = cand_rank - base_rank
    movement = np.abs(delta)

    turnover: Dict[str, Any] = {}
    for size in top_n:
        base_top = {labels[i] for i in np.argsort(base_rank)[:size]}
        cand_top = {labels[i] for i in np.argsort(cand_rank)[:size]}
        turnover["top%d" % size] = {
            "overlap": len(base_top & cand_top),
            "turnover": size - len(base_top & cand_top),
            "entered": sorted(cand_top - base_top),
            "left": sorted(base_top - cand_top),
        }

    order = np.argsort(delta)
    risers = [{"label": labels[i], "baselineRank": float(base_rank[i]),
               "candidateRank": float(cand_rank[i]), "delta": float(delta[i])}
              for i in order[:5]]
    fallers = [{"label": labels[i], "baselineRank": float(base_rank[i]),
                "candidateRank": float(cand_rank[i]), "delta": float(delta[i])}
               for i in order[::-1][:5]]
    return {
        "spearman": spearman(base, cand),
        "kendallTau": kendall_tau(base, cand),
        "medianAbsoluteMovement": float(np.median(movement)),
        "meanAbsoluteMovement": float(movement.mean()),
        "maxMovement": float(movement.max()),
        "movedAtAll": int(np.sum(movement > 0)),
        "turnover": turnover,
        "largestRisers": risers,
        "largestFallers": fallers,
    }


def variance_contribution(components: Mapping[str, Sequence[float]],
                          weights: Mapping[str, float]) -> Dict[str, Any]:
    """How much of the composite's variance each weighted pillar really carries.

    The Phase-21 trap is a pillar with a nominal 10% weight that behaves like
    30% because its normalized spread is three times wider than its peers'. The
    covariance decomposition is the honest answer: each pillar's share is
    ``cov(w_i * x_i, total) / var(total)``, and the shares sum to 1 exactly.
    """
    weighted = {name: np.asarray([float(v) for v in values], dtype=np.float64)
                * float(weights.get(name, 0.0))
                for name, values in components.items()}
    total = sum(weighted.values())
    total_variance = float(np.var(total, ddof=1))
    shares: Dict[str, Any] = {}
    for name, column in weighted.items():
        covariance = float(np.cov(column, total, ddof=1)[0, 1])
        shares[name] = {
            "nominalWeight": float(weights.get(name, 0.0)),
            "weightedStd": float(column.std(ddof=1)),
            "varianceShare": covariance / total_variance if total_variance else None,
        }
    return {"totalStd": float(total.std(ddof=1)), "shares": shares}
