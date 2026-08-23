"""Part 25: the Central Limit Theorem comparison.

WHAT THIS IS FOR
----------------
Research validation only. The CLT answer to "how many packs until EV is
representative" is the textbook one:

    one-sided realization, P(Xbar_N >= r*mu) >= c:
        Xbar_N ~approx~ Normal(mu, sigma^2 / N)
        P(Xbar_N >= r*mu) = Phi( (1-r) * mu * sqrt(N) / sigma )
        => N >= ( z_c * sigma / ((1-r) * mu) )^2

    two-sided convergence, P(|Xbar_N/mu - 1| <= tau) >= c:
        => N >= ( z_{(1+c)/2} * sigma / (tau * mu) )^2

Both are just ``N >= (z * CV / delta)^2``: the required sample size scales with
the SQUARE of the coefficient of variation. For the live cohort, whose CV spans
roughly 1.9 to 11.7, that alone predicts a ~38x spread in horizons.

WHY IT IS NEVER THE REPORTED ANSWER
-----------------------------------
The normal approximation assumes Xbar_N is symmetric around mu. At realistic N
these distributions are emphatically not: a set where 64% of all economic value
comes from the top 1% of packs has a sample mean that is itself violently
right-skewed at N = 36, so the true P(Xbar_N >= 0.8*mu) sits BELOW what the
symmetric approximation predicts - the median of Xbar_N runs under mu, and no
amount of algebra on sigma sees that.

The point of computing it anyway is the comparison itself, which is a genuine
research finding: the ratio of empirical to CLT horizon measures how badly the
asymptotics mislead at human opening quantities, and where that ratio approaches
1 marks the N at which the approximation finally becomes usable for this asset
class.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any, Dict, Mapping, Optional, Sequence

_NORMAL = NormalDist()


def normal_quantile(p: float) -> float:
    """Standard-normal inverse CDF.

    ``statistics.NormalDist`` rather than SciPy: it is in the standard library,
    the backend does not otherwise depend on SciPy, and adding a dependency for
    one quantile would be a poor trade.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"normal quantile requires p in (0, 1); got {p}")
    return _NORMAL.inv_cdf(p)


@dataclass(frozen=True)
class CltHorizon:
    kind: str  # 'realization' | 'convergence'
    parameter: float  # r for realization, tau for convergence
    confidence: float
    z: float
    required_n: Optional[int]
    note: Optional[str] = None

    def as_payload(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "parameter": self.parameter,
            "confidence": self.confidence,
            "z": self.z,
            "requiredN": self.required_n,
            "note": self.note,
        }


def clt_realization_horizon(
    *, ev: float, std_dev: float, target: float, confidence: float
) -> CltHorizon:
    """``N ~= (z_c * sigma / ((1-r) * mu))^2``."""
    z = normal_quantile(confidence)
    delta = 1.0 - float(target)
    if delta <= 0.0:
        # r >= 1 asks how many packs until the average EXCEEDS the mean, which
        # the symmetric approximation answers with "half of openers, at every N".
        # There is no finite N, and saying so beats emitting a huge number.
        return CltHorizon("realization", float(target), float(confidence), z, None,
                          note="no finite CLT horizon for r >= 1 under a symmetric approximation")
    return _horizon_from_delta("realization", float(target), float(confidence), z, ev, std_dev, delta)


def clt_convergence_horizon(
    *, ev: float, std_dev: float, tolerance: float, confidence: float
) -> CltHorizon:
    """``N ~= (z_{(1+c)/2} * sigma / (tau * mu))^2``.

    The two-sided z is the point people most often get wrong: requiring 80% of
    openers INSIDE a band needs ``z_{0.90} = 1.2816``, not ``z_{0.80} = 0.8416``,
    because 20% of the mass is split between two tails.
    """
    z = normal_quantile((1.0 + float(confidence)) / 2.0)
    return _horizon_from_delta(
        "convergence", float(tolerance), float(confidence), z, ev, std_dev, float(tolerance)
    )


def _horizon_from_delta(
    kind: str, parameter: float, confidence: float, z: float,
    ev: float, std_dev: float, delta: float,
) -> CltHorizon:
    ev_f = float(ev)
    sigma = float(std_dev)
    if not math.isfinite(ev_f) or ev_f <= 0.0:
        return CltHorizon(kind, parameter, confidence, z, None, note="degenerate EV")
    if not math.isfinite(sigma) or sigma <= 0.0:
        # A constant distribution is already exactly at its mean at N = 1.
        return CltHorizon(kind, parameter, confidence, z, 1, note="zero variance")
    if z <= 0.0:
        # c <= 0.5 one-sided: the approximation says the median opener already
        # qualifies, so N = 1. Recorded rather than silently clamped.
        return CltHorizon(kind, parameter, confidence, z, 1,
                          note="confidence at or below the symmetric centre")
    required = (z * sigma / (delta * ev_f)) ** 2
    if not math.isfinite(required):
        return CltHorizon(kind, parameter, confidence, z, None, note="non-finite requirement")
    return CltHorizon(kind, parameter, confidence, z, max(1, int(math.ceil(required))))


def build_clt_comparison(
    *,
    ev: float,
    std_dev: float,
    realization_targets: Sequence[float],
    convergence_tolerances: Sequence[float],
    confidence_levels: Sequence[float],
    empirical_horizons: Mapping[str, Optional[int]] | None = None,
) -> Dict[str, Any]:
    """The full CLT grid plus, where available, its ratio to the empirical answer.

    ``empirical_horizons`` is keyed ``"<metric_key}|{confidence}"`` to match the
    horizon records. A ratio above 1 means the real distribution needed MORE
    packs than the asymptotics promised - which is the expected direction for
    right-skewed openings, and the size of the excess is the finding.
    """
    horizons: Dict[str, Any] = {"realization": {}, "convergence": {}}
    ratios: Dict[str, Any] = {}
    lookup = dict(empirical_horizons or {})

    for target in realization_targets:
        bucket: Dict[str, Any] = {}
        for confidence in confidence_levels:
            result = clt_realization_horizon(
                ev=ev, std_dev=std_dev, target=target, confidence=confidence
            )
            bucket[f"{confidence:.2f}"] = result.as_payload()
            key = f"realization_ge_{target:.2f}|{confidence:.2f}"
            ratios[key] = _ratio(lookup.get(key), result.required_n)
        horizons["realization"][f"{target:.2f}"] = bucket

    for tolerance in convergence_tolerances:
        bucket = {}
        for confidence in confidence_levels:
            result = clt_convergence_horizon(
                ev=ev, std_dev=std_dev, tolerance=tolerance, confidence=confidence
            )
            bucket[f"{confidence:.2f}"] = result.as_payload()
            key = f"within_tau_{tolerance:.2f}|{confidence:.2f}"
            ratios[key] = _ratio(lookup.get(key), result.required_n)
        horizons["convergence"][f"{tolerance:.2f}"] = bucket

    return {
        "horizons": horizons,
        "empiricalOverCltRatio": ratios,
        "model": "normal_approximation_of_the_sample_mean",
        "usedAsReportedHorizon": False,
    }


def _ratio(empirical: Optional[int], clt: Optional[int]) -> Optional[float]:
    if empirical is None or clt is None or clt <= 0:
        return None
    return float(empirical) / float(clt)
