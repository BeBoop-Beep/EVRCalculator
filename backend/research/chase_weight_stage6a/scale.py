"""Phase 2 and 13: what the Chase scale actually is, and what it costs.

RESEARCH ONLY. Nothing here is read by production.

THE FINDING THIS MODULE EXISTS TO MAKE UNMISSABLE
--------------------------------------------------
Stage VI reported that a nominal 10% Chase weight bought roughly 25% of the
composite's variance, and left that as an unexplained "leverage" property of the
pillar. It is not mysterious. It is dispersion:

    Financial RIP V4    cohort sd ~  8.4   (occupies about 10-57 of its 0-100 range)
    Collector Appeal V5 cohort sd ~ 10.9   (occupies about 49-99)
    Chase Opportunity   cohort sd ~ 28.0   (occupies 0-117)

A weighted sum does not care what a pillar's nominal range is; it cares about
``w * sd``. Chase's spread is roughly 3.3x Financial's, so one nominal Chase
point moves the ranking about 3.3 times as far as one nominal Financial point.
The "leverage ratio" Stage VI measured is that ratio, squared and renormalized.

That distinction - **scaling problem, not weight problem** - is what Phase 13
asks for, and :func:`dispersion_equivalent_weight` is the arithmetic that
separates them.

THE TRANSFORM DEFECT
--------------------
The approved transform is ``200K / (K + 10)``. As a formula it crosses 100 at
K = 10 and reaches 116.67 at the cohort maximum of K = 14. The Stage VI
implementation clamped it to [0, 100] and its docstring claimed the curve
"never reaches 100", which is true of ``100K/(K+s)`` and false of the formula
actually approved and shipped into the study.

So the approved construct is ambiguous between two different pillars, and
:data:`TRANSFORM_VARIANTS` holds both plus the honest third option, because
Phase 2 requires the question to be answered rather than silently resolved:

* ``approved_unclamped``  - the formula as written, a saturating index to ~117
* ``approved_clamped``    - the formula as implemented, flat above K = 10
* ``rescaled_0_100``      - ``100K/(K+10)``, a conventional 0-100 pillar that
                            never saturates and never needs a clamp
"""

from __future__ import annotations

import math
import statistics as st
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import numpy as np

#: The saturation constant Stage VI approved. Not reopened here.
SATURATION = 10.0

#: The K values Phase 2 requires reported, whatever the cohort happens to hold.
REPRESENTATIVE_K = (0, 1, 2, 3, 5, 10, 15, 20, 30)


def approved_unclamped(k: Any, *, saturation: float = SATURATION) -> float:
    """``200K / (K + 10)``, exactly as approved on paper. Exceeds 100 for K > 10."""
    count = _count(k)
    return 200.0 * count / (count + saturation) if count > 0 else 0.0


def approved_clamped(k: Any, *, saturation: float = SATURATION) -> float:
    """The formula as Stage VI actually implemented it: clamped at 100.

    Flat for every K >= 10, which in this cohort collapses five distinct
    products onto one score.
    """
    return min(100.0, approved_unclamped(k, saturation=saturation))


def rescaled_0_100(k: Any, *, saturation: float = SATURATION) -> float:
    """``100K / (K + 10)``. Same shape, same saturation constant, honest ceiling.

    Asymptotic to 100 and never reaching it, which is the property Stage VI's
    docstring claimed for the approved formula. Halves the dispersion, and
    therefore halves the leverage, without changing any product's ORDER.
    """
    count = _count(k)
    return 100.0 * count / (count + saturation) if count > 0 else 0.0


def _count(value: Any) -> float:
    try:
        count = float(value)
    except (TypeError, ValueError):
        return 0.0
    if count != count or count in (float("inf"), float("-inf")) or count <= 0:
        return 0.0
    return count


TRANSFORM_VARIANTS: Dict[str, Callable[..., float]] = {
    "approved_unclamped": approved_unclamped,
    "approved_clamped": approved_clamped,
    "rescaled_0_100": rescaled_0_100,
}


def describe(values: Sequence[float]) -> Dict[str, Optional[float]]:
    """The full Phase-2 distribution report for one column."""
    array = np.asarray([float(v) for v in values], dtype=np.float64)
    if array.size == 0:
        return {}
    def q(p: float) -> float:
        return float(np.percentile(array, p))
    return {
        "n": int(array.size),
        "min": float(array.min()), "p5": q(5), "p10": q(10), "p25": q(25),
        "median": q(50), "p75": q(75), "p90": q(90), "p95": q(95),
        "max": float(array.max()),
        "mean": float(array.mean()),
        "sd": float(array.std(ddof=1)) if array.size > 1 else 0.0,
        "range": float(array.max() - array.min()),
    }


def dispersion_equivalent_weight(*, reference_sd: float, pillar_sd: float,
                                 reference_weight: float,
                                 nominal_weight: float) -> Dict[str, Any]:
    """What a nominal weight is really worth, in units of the reference pillar.

    ``effectiveAsReference`` answers: to move the composite as much as this
    nominal Chase weight does, how much weight would a pillar with FINANCIAL's
    dispersion need? That number, not the nominal one, is what a reader means by
    "Chase is 5% of the score".

    ``dispersionRatio`` is the whole leverage story in one number. A ratio of 1
    would mean nominal weight and influence coincide.
    """
    if reference_sd <= 0:
        return {"supported": False, "reason": "reference pillar has no dispersion"}
    ratio = pillar_sd / reference_sd
    return {
        "supported": True,
        "dispersionRatio": ratio,
        "nominalWeight": nominal_weight,
        "effectiveAsReference": nominal_weight * ratio,
        "weightForParity": (reference_weight / ratio) if ratio else None,
        "referenceSd": reference_sd,
        "pillarSd": pillar_sd,
    }


def scale_audit(*, core_k: Sequence[int], pillars: Mapping[str, Sequence[float]]
                ) -> Dict[str, Any]:
    """Phase 2 in one object: every transform variant against the real pillars."""
    variants: Dict[str, Any] = {}
    for name, function in TRANSFORM_VARIANTS.items():
        values = [function(k) for k in core_k]
        block = describe(values)
        block["distinctScores"] = len({round(v, 9) for v in values})
        block["atCeiling"] = sum(1 for v in values if v >= 99.999999)
        variants[name] = block

    reference = describe(pillars["financialRip"])
    for name, block in variants.items():
        block["dispersion"] = dispersion_equivalent_weight(
            reference_sd=reference["sd"], pillar_sd=block["sd"],
            reference_weight=0.90, nominal_weight=0.05)

    return {
        "coreK": describe([float(k) for k in core_k]),
        "pillars": {name: describe(values) for name, values in pillars.items()},
        "variants": variants,
        "representative": {
            str(k): {name: function(k) for name, function in TRANSFORM_VARIANTS.items()}
            for k in REPRESENTATIVE_K
        },
        "maxObservedK": int(max(core_k)) if len(core_k) else None,
        "clampCollisions": sum(1 for k in core_k if float(k) > SATURATION),
    }
