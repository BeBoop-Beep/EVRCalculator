"""Stage XI - Hill spectrum, HHI concentration contribution, and EVT tails.

RESEARCH ONLY. No sealed-product economic variable is read anywhere.

WHAT THIS STAGE TESTS
---------------------
Stages IX and X both failed to produce a discrete Core/Extended roster. This
module tests two replacements:

  1. a CONTINUOUS card-level quantity, the share of the set's measured value
     concentration that one card is responsible for;
  2. EXTREME VALUE THEORY tail selection, which - unlike a mixture model - does
     not need the chase tier to be a second population competing for likelihood.

THE ORDERING CAVEAT, STATED UP FRONT
------------------------------------
    HC_i = s_i^2 / HHI

is a strictly increasing function of s_i on positive shares, so ranking cards by
HC is IDENTICAL to ranking them by value share, which is identical to ranking
them by price. HC therefore adds no new ordering information. What it changes is
the SCALE and the INTERPRETATION: it is a decomposition of a validated set
statistic back onto its causes, and it sums to one. Any claim that HC "finds"
chase cards better than price must be treated as a claim about interpretability,
never about discrimination.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Shares, HHI and the Hill spectrum
# ---------------------------------------------------------------------------

def shares(values: Sequence[float]) -> np.ndarray:
    v = np.asarray([float(t) for t in values if t and float(t) > 0.0], dtype=float)
    return v / v.sum()


def hhi(s: np.ndarray) -> float:
    return float((s ** 2).sum())


def hill_numbers(s: np.ndarray) -> Dict[str, float]:
    """Effective counts at increasing q. Higher q ignores the bulk harder."""
    s = s[s > 0]
    d1 = float(np.exp(-(s * np.log(s)).sum()))
    d2 = 1.0 / float((s ** 2).sum())
    d3 = float((s ** 3).sum()) ** (-0.5)
    d4 = float((s ** 4).sum()) ** (-1.0 / 3.0)
    dinf = 1.0 / float(s.max())
    return {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "Dinf": dinf,
            "D2_minus_D4": d2 - d4, "D2_over_D4": d2 / d4 if d4 else float("nan")}


# ---------------------------------------------------------------------------
# HHI concentration contribution
# ---------------------------------------------------------------------------

def concentration_contribution(s: np.ndarray) -> np.ndarray:
    """HC_i = s_i^2 / HHI. Sums to exactly 1."""
    return (s ** 2) / hhi(s)


def contributor_effective_count(hc: np.ndarray) -> float:
    """N_HC = 1 / sum(HC^2) - effective number of concentration DRIVERS.

    Algebraically N_HC = D4^3 / D2^2, so it is a fixed function of the Hill
    spectrum rather than independent information. Asserted in the test suite.
    """
    return 1.0 / float((hc ** 2).sum())


def hc_profile(values: Sequence[float]) -> Dict[str, object]:
    s = np.sort(shares(values))[::-1]
    hc = concentration_contribution(s)
    cum = np.cumsum(hc)

    def cards_for(frac: float) -> int:
        idx = np.searchsorted(cum, frac)
        return int(min(idx + 1, hc.size))

    return {
        "n": int(s.size),
        "hhi": hhi(s),
        "hill": hill_numbers(s),
        "nHC": contributor_effective_count(hc),
        "hcTop1": float(hc[0]),
        "hcTop2": float(hc[:2].sum()),
        "hcTop3": float(hc[:3].sum()),
        "hcTop5": float(hc[:5].sum()),
        "hcTop10": float(hc[:10].sum()),
        "hcMedian": float(np.median(hc)),
        "hcTopOverMedian": float(hc[0] / np.median(hc)) if np.median(hc) > 0 else float("inf"),
        "cardsFor25": cards_for(0.25), "cardsFor50": cards_for(0.50),
        "cardsFor75": cards_for(0.75), "cardsFor90": cards_for(0.90),
        "hc": hc,
    }


# ---------------------------------------------------------------------------
# Phase 5 - card removal influence
# ---------------------------------------------------------------------------

def removal_influence(values: Sequence[float], top: int = 15) -> List[Dict[str, float]]:
    """Change in 1/HHI when one card is removed and shares renormalised."""
    v = np.sort(np.asarray([float(t) for t in values if t and float(t) > 0.0]))[::-1]
    base = 1.0 / hhi(v / v.sum())
    out = []
    for i in range(min(top, v.size)):
        rest = np.delete(v, i)
        out.append({"rank": i + 1, "value": float(v[i]),
                    "deltaEffectiveCount": float(1.0 / hhi(rest / rest.sum()) - base)})
    return out


# ---------------------------------------------------------------------------
# Phase 6 - EVT: peaks over threshold with a Generalised Pareto fit
# ---------------------------------------------------------------------------

def gpd_fit(exceedances: np.ndarray) -> Optional[Dict[str, float]]:
    """Probability-weighted-moment GPD fit. Robust at the tiny sample sizes
    a chase tail actually provides, unlike MLE."""
    y = np.sort(np.asarray(exceedances, dtype=float))
    n = y.size
    if n < 5 or y.max() <= 0:
        return None
    b0 = y.mean()
    p = (np.arange(1, n + 1) - 0.35) / n
    b1 = float((p * y).sum() / n)
    denom = b0 - 2.0 * b1
    if abs(denom) < 1e-12:
        return None
    k = b0 / denom - 2.0            # shape, xi = -k in this parameterisation
    a = 2.0 * b0 * b1 / denom
    if a <= 0:
        return None
    return {"scale": float(a), "shape": float(-k), "n": int(n)}


def hill_estimator(values: Sequence[float], k: int) -> Optional[float]:
    """Hill tail index using the top k order statistics."""
    v = np.sort(np.asarray([float(t) for t in values if t and float(t) > 0.0]))[::-1]
    if k < 2 or k >= v.size:
        return None
    logs = np.log(v[:k + 1])
    return float((logs[:k] - logs[k]).mean())


def hill_stability(values: Sequence[float], ks: Sequence[int]) -> Dict[int, Optional[float]]:
    return {k: hill_estimator(values, k) for k in ks}


def mean_excess(values: Sequence[float], thresholds: Sequence[float]
                ) -> List[Dict[str, float]]:
    v = np.asarray([float(t) for t in values if t and float(t) > 0.0])
    out = []
    for u in thresholds:
        ex = v[v > u] - u
        if ex.size >= 3:
            out.append({"threshold": float(u), "nExceed": int(ex.size),
                        "meanExcess": float(ex.mean())})
    return out


def evt_tail(values: Sequence[float], *, min_exceed: int = 8,
             max_fraction: float = 0.25) -> Dict[str, object]:
    """Select an upper-tail threshold by Hill-plot stability.

    Chooses the threshold whose Hill index is most stable across a neighbouring
    window, rather than the one producing a wanted card count. Returns the
    diagnostics needed to judge whether the choice is credible at all.
    """
    v = np.sort(np.asarray([float(t) for t in values if t and float(t) > 0.0]))[::-1]
    n = v.size
    kmax = int(max(min_exceed, min(n - 2, math.floor(n * max_fraction))))
    if n < 30 or kmax <= min_exceed:
        return {"supported": False, "reason": "too few observations for a tail fit",
                "n": int(n)}

    ks = list(range(min_exceed, kmax + 1))
    hills = {k: hill_estimator(v, k) for k in ks}
    usable = [k for k in ks if hills[k] and hills[k] > 0]
    if len(usable) < 5:
        return {"supported": False, "reason": "Hill estimator unusable", "n": int(n)}

    # Most stable window: lowest local coefficient of variation of the Hill index.
    win = 5
    best_k, best_cv = None, float("inf")
    for i in range(len(usable) - win + 1):
        block = [hills[k] for k in usable[i:i + win]]
        m = float(np.mean(block))
        cv = float(np.std(block) / m) if m > 0 else float("inf")
        if cv < best_cv:
            best_cv, best_k = cv, usable[i + win // 2]

    u = float(v[best_k])
    gpd = gpd_fit(v[:best_k] - u)
    return {"supported": True, "n": int(n), "tailK": int(best_k),
            "threshold": u, "hillIndex": hills[best_k], "hillCv": best_cv,
            "gpd": gpd, "tailFraction": best_k / n,
            "hillPlot": {k: (round(hills[k], 4) if hills[k] else None) for k in ks}}
