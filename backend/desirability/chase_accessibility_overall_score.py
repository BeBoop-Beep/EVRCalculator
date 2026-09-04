"""Chase Accessibility Overall-score transform - production scoring helper.

PRODUCTION MODULE, and the ONLY place raw Chase Accessibility becomes an
Overall-RIP-scale ``A_score``. Nothing else in this codebase may reimplement
``100 * A_raw / (A_raw + k)`` - every consumer of the transformed value must
import :func:`chase_accessibility_overall_score` from here.

THE TRANSFORM
--------------
    A_score(k) = 100 * A_raw / (A_raw + k),  k = CHASE_ACCESSIBILITY_OVERALL_SCORE_K

Locked by research (``docs/research/OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_
CLOSURE.md``, FINAL CLOSURE section F2): a fixed, cohort-independent anchor,
never re-derived from an observed cohort's min/max or percentile rank. As new
sets enter, their ``A_score`` is computed from the same fixed ``k`` with no
re-anchoring, so a score-50 set today stays comparable to a score-50 set found
next month.

SCALE SEPARATION
-----------------
The PUBLIC Chase Accessibility metric
(:mod:`backend.desirability.chase_accessibility`) stays raw - a decimal
fraction such as 0.002 = 0.20% - everywhere it is currently exposed. This
module's ``A_score`` is a DISTINCT, Overall-RIP-scoring-only quantity and must
never be presented as, or substituted for, the raw public metric.

MISSING / INVALID INPUT
------------------------
Following the convention already used throughout
``backend/desirability/chase_accessibility.py`` and ``weighted_rip.py``: a
missing or non-finite ``A_raw`` returns ``None`` (never coerced to 0.0), and a
negative ``A_raw`` is refused (returns ``None``) rather than clamped - clamping
is exactly how an out-of-domain value gets silently accepted as a valid score
elsewhere in this codebase (see ``chase_accessibility._valid_probability``'s
docstring on why odds columns must be refused, not clamped).

No additional clamp is applied to the transform's output beyond that domain
refusal: for any finite ``A_raw >= 0`` and ``k > 0``, ``A_score`` is
mathematically bounded to ``[0, 100)`` by construction (the fraction
``A_raw / (A_raw + k)`` cannot reach 1 for finite ``A_raw``), so an additional
clamp would never bind and is not added.
"""

from __future__ import annotations

import math
from typing import Any, Optional

#: The published transform identity. Stored/attached anywhere A_score is
#: computed, so a value can never be read without the model that produced it.
CHASE_ACCESSIBILITY_OVERALL_SCORE_VERSION = (
    "chase_accessibility_overall_score_v1_saturating_k002"
)

#: Fixed anchor. Locked by research as the geometric center of a pre-registered
#: log2-uniform grid ({0.0005, 0.001, 0.002, 0.004, 0.008}), NOT fit to any
#: cohort's observed A_raw distribution. Never re-derived at runtime.
CHASE_ACCESSIBILITY_OVERALL_SCORE_K = 0.002


def _finite(value: Any) -> Optional[float]:
    """A finite float, or None. Mirrors chase_accessibility._finite exactly."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def chase_accessibility_overall_score(
    a_raw: Any, *, k: float = CHASE_ACCESSIBILITY_OVERALL_SCORE_K
) -> Optional[float]:
    """``A_score = 100 * A_raw / (A_raw + k)`` - the ONE canonical implementation.

    ``a_raw`` is the raw, decimal-fraction Chase Accessibility value (the
    ``accessibility`` field of
    :func:`backend.desirability.chase_accessibility.compute_chase_accessibility`,
    NOT ``accessibilityPct``). Deterministic, monotonic in ``a_raw``, no
    percentile/rank normalization, no observed-cohort min/max.

    Returns ``None`` (never 0.0) when ``a_raw`` is missing, non-finite, or
    negative - a missing Accessibility is a different fact from a measured
    zero and must never be conflated with one. Returns ``None`` if ``k`` is
    not strictly positive, since the transform is undefined/degenerate there.
    """
    value = _finite(a_raw)
    if value is None or value < 0.0:
        return None
    anchor = _finite(k)
    if anchor is None or anchor <= 0.0:
        return None
    return 100.0 * value / (value + anchor)
