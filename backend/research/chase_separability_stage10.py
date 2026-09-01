"""Stage X - chase separability: is there a distinct chase tier at all?

RESEARCH ONLY. Nothing here is read by production, and no sealed-product
economic variable enters anywhere in this module (Phase 15 - product invariance
is absolute).

THE QUESTION THIS ANSWERS
------------------------
Stage IX established that 1/HHI is a good CONTINUOUS depth descriptor and that
every tested roster rule failed cross-era, because flat sets have no boundary to
find and a rule obliged to emit one invents it. So this module does not ask
"where does the chase tier end". It asks, first:

    is the upper-value population statistically distinguishable from the
    ordinary-card population at all?

Only sets that pass that test are eligible for a roster.

WHY log VALUE
-------------
Membership must be invariant to uniform price scaling. Multiplying every price
by c shifts log value by log(c), which moves every component mean equally and
leaves component ASSIGNMENTS - and therefore rosters - exactly unchanged. Any
rule stated in raw dollars fails this.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import numpy as np

#: Minimum fraction of the set a component must hold to count as a real
#: population rather than a fitted noise pocket.
MIN_COMPONENT_FRACTION = 0.02

#: Minimum absolute membership. Two cards is not a population.
MIN_COMPONENT_COUNT = 3

#: BIC improvement required before accepting an extra component. More
#: parameters almost always raise the likelihood; this is the toll.
MIN_DELTA_BIC = 10.0

#: Ashman D >= 2 is the standard threshold for a genuinely bimodal separation
#: between two Gaussians.
MIN_ASHMAN_D = 2.0

#: Mean posterior confidence required for the upper component's members.
MIN_POSTERIOR = 0.80

#: Variance floor, so a component cannot collapse onto a single point.
VAR_FLOOR = 1e-4


# ---------------------------------------------------------------------------
# 1-D Gaussian mixture by EM
# ---------------------------------------------------------------------------

def fit_gmm(x: np.ndarray, k: int, *, iters: int = 300, seed: int = 0
            ) -> Optional[Dict[str, np.ndarray]]:
    """Fit a k-component 1-D Gaussian mixture. Deterministic quantile init."""
    x = np.asarray(x, dtype=float)
    n = x.size
    if n < k * MIN_COMPONENT_COUNT:
        return None
    if k == 1:
        mu = np.array([x.mean()])
        var = np.array([max(x.var(ddof=0), VAR_FLOOR)])
        w = np.array([1.0])
        return {"mu": mu, "var": var, "w": w, "loglik": _loglik(x, mu, var, w), "k": 1}

    qs = np.linspace(0.0, 1.0, k + 2)[1:-1]
    mu = np.quantile(x, qs).astype(float)
    var = np.full(k, max(x.var(ddof=0), VAR_FLOOR))
    w = np.full(k, 1.0 / k)

    prev = -np.inf
    for _ in range(iters):
        resp = _responsibilities(x, mu, var, w)
        nk = resp.sum(axis=0) + 1e-12
        w = nk / n
        mu = (resp * x[:, None]).sum(axis=0) / nk
        var = np.maximum((resp * (x[:, None] - mu) ** 2).sum(axis=0) / nk, VAR_FLOOR)
        ll = _loglik(x, mu, var, w)
        if not np.isfinite(ll):
            return None
        if abs(ll - prev) < 1e-9:
            break
        prev = ll

    order = np.argsort(mu)
    return {"mu": mu[order], "var": var[order], "w": w[order],
            "loglik": _loglik(x, mu[order], var[order], w[order]), "k": k}


def _component_pdf(x: np.ndarray, mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * (x[:, None] - mu) ** 2 / var) / np.sqrt(2.0 * np.pi * var)


def _responsibilities(x, mu, var, w) -> np.ndarray:
    p = _component_pdf(x, mu, var) * w
    total = p.sum(axis=1, keepdims=True)
    total[total <= 0] = 1e-300
    return p / total


def _loglik(x, mu, var, w) -> float:
    p = (_component_pdf(x, mu, var) * w).sum(axis=1)
    p[p <= 0] = 1e-300
    return float(np.log(p).sum())


def bic(fit: Dict[str, np.ndarray], n: int) -> float:
    """Lower is better. 3k-1 free parameters for a k-component 1-D mixture."""
    params = 3 * int(fit["k"]) - 1
    return -2.0 * float(fit["loglik"]) + params * math.log(n)


def ashman_d(mu1: float, mu2: float, v1: float, v2: float) -> float:
    return abs(mu2 - mu1) * math.sqrt(2.0 / (v1 + v2))


# ---------------------------------------------------------------------------
# Silverman's critical-bandwidth bootstrap test for unimodality
# ---------------------------------------------------------------------------

def _n_modes(x: np.ndarray, h: float, grid: int = 512) -> int:
    lo, hi = x.min() - 3 * h, x.max() + 3 * h
    g = np.linspace(lo, hi, grid)
    d = np.exp(-0.5 * ((g[:, None] - x[None, :]) / h) ** 2).sum(axis=1)
    return int(((d[1:-1] > d[:-2]) & (d[1:-1] >= d[2:])).sum())


def critical_bandwidth(x: np.ndarray, max_modes: int = 1) -> float:
    """Smallest h whose Gaussian KDE has <= max_modes modes."""
    lo, hi = 1e-4, max(x.std(ddof=0) * 5.0, 1.0)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _n_modes(x, mid) > max_modes:
            lo = mid
        else:
            hi = mid
    return hi


def silverman_test(x: np.ndarray, *, boot: int = 200, seed: int = 0) -> float:
    """p-value against H0: the distribution is unimodal. Small p => multimodal."""
    x = np.asarray(x, dtype=float)
    n = x.size
    if boot <= 0:
        return float("nan")  # caller opted out; stability loops do not need it
    h = critical_bandwidth(x)
    rng = np.random.default_rng(seed)
    sd = x.std(ddof=0)
    if sd <= 0:
        return 1.0
    count = 0
    for _ in range(boot):
        idx = rng.integers(0, n, n)
        y = x[idx] + h * rng.standard_normal(n)
        y = x.mean() + (y - y.mean()) / math.sqrt(1.0 + h * h / (sd * sd))
        if critical_bandwidth(y) >= h:
            count += 1
    return count / boot


# ---------------------------------------------------------------------------
# The separability decision
# ---------------------------------------------------------------------------

STATE_CORE = "CORE_SEPARABLE"
STATE_CORE_EXT = "CORE_AND_EXTENDED_SEPARABLE"
STATE_CONTINUOUS = "UPPER_TAIL_PRESENT_BUT_CONTINUOUS"
STATE_DISTRIBUTED = "DISTRIBUTED_VALUE"


def evaluate_separability(values: Sequence[float], *, boot: int = 120,
                          seed: int = 0) -> Dict[str, object]:
    """Classify a set's value distribution before any roster is attempted."""
    v = np.asarray([float(t) for t in values if t and float(t) > 0.0], dtype=float)
    n = v.size
    if n < 20:
        return {"state": None, "reason": "too few priced cards", "n": int(n)}

    x = np.log(v)
    fits = {k: fit_gmm(x, k, seed=seed) for k in (1, 2, 3)}
    bics = {k: (bic(f, n) if f else math.inf) for k, f in fits.items()}

    best_k, gates = 1, {}
    f2 = fits[2]
    if f2 is not None:
        d2 = ashman_d(f2["mu"][0], f2["mu"][1], f2["var"][0], f2["var"][1])
        resp = _responsibilities(x, f2["mu"], f2["var"], f2["w"])
        upper = resp.argmax(axis=1) == 1
        gates["deltaBic_1_2"] = bics[1] - bics[2]
        gates["ashmanD_2"] = d2
        gates["upperCount"] = int(upper.sum())
        gates["upperFraction"] = float(upper.mean())
        gates["upperPosterior"] = float(resp[upper, 1].mean()) if upper.any() else 0.0
        if (gates["deltaBic_1_2"] >= MIN_DELTA_BIC
                and d2 >= MIN_ASHMAN_D
                and gates["upperCount"] >= MIN_COMPONENT_COUNT
                and gates["upperFraction"] >= MIN_COMPONENT_FRACTION
                and gates["upperPosterior"] >= MIN_POSTERIOR):
            best_k = 2

    f3 = fits[3]
    if best_k == 2 and f3 is not None:
        resp3 = _responsibilities(x, f3["mu"], f3["var"], f3["w"])
        lab = resp3.argmax(axis=1)
        d23 = ashman_d(f3["mu"][1], f3["mu"][2], f3["var"][1], f3["var"][2])
        sizes = [int((lab == i).sum()) for i in range(3)]
        gates["deltaBic_2_3"] = bics[2] - bics[3]
        gates["ashmanD_23"] = d23
        gates["sizes_3"] = sizes
        if (gates["deltaBic_2_3"] >= MIN_DELTA_BIC and d23 >= MIN_ASHMAN_D
                and min(sizes) >= MIN_COMPONENT_COUNT
                and min(sizes) / n >= MIN_COMPONENT_FRACTION):
            best_k = 3

    p_uni = silverman_test(x, boot=boot, seed=seed)

    if best_k == 1:
        # Top-heavy but not separable, versus genuinely flat.
        share = v / v.sum()
        state = (STATE_CONTINUOUS if float(np.sort(share)[-1]) >= 0.15
                 else STATE_DISTRIBUTED)
        roster = None
    else:
        state = STATE_CORE if best_k == 2 else STATE_CORE_EXT
        fit = fits[best_k]
        lab = _responsibilities(x, fit["mu"], fit["var"], fit["w"]).argmax(axis=1)
        core = np.sort(v[lab == best_k - 1])[::-1]
        ext = np.sort(v[lab == best_k - 2])[::-1] if best_k == 3 else None
        roster = {"coreCount": int(core.size), "corePrices": core.tolist()[:12],
                  "extendedCount": int(ext.size) if ext is not None else None}

    return {"state": state, "n": int(n), "selectedK": best_k,
            "bic": {k: (None if math.isinf(b) else round(b, 2)) for k, b in bics.items()},
            "silvermanP": round(p_uni, 4), "gates": gates, "roster": roster}
