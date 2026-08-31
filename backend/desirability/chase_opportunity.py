"""Chase Opportunity - the production Chase pillar of Overall RIP V11.

PRODUCTION MODULE. Nothing here imports from ``backend.research``.

The Stage V-C -> VI -> VI-A -> VI-B research lineage validated a Chase pillar
built from ONE input: the product's Core chase count ``K``. This module is the
production promotion of that construction. The research modules remain the
parity reference and are never on a canonical path.

THE TRANSFORM
-------------
    Chase Opportunity = 100 * K / (K + 10)

NO CLAMP. The transform is bounded above by 100 for every finite ``K``, so a
clamp is unreachable rather than merely unused - and Stage VI-B established
that clamping the older ``200K/(K+10)`` scale destroyed top-end differentiation
by collapsing five distinct products onto 100. Equal ``K`` yields equal score,
which is a legitimate tie; no tie here is an artifact of bounding.

    K =  0  ->   0.000000
    K =  1  ->   9.090909
    K =  2  ->  16.666667
    K =  5  ->  33.333333
    K = 10  ->  50.000000
    K = 14  ->  58.333333

DO NOT REUSE THE STAGE VI SCALE. ``200K/(K+10)`` exceeds 100 and is not a valid
0-100 pillar score. It survives only inside historical research tests.

MISSING IS NOT ZERO
-------------------
A validly evaluated Core basket that admits no card is ``K = 0``, score ``0``,
status ``ready`` - the product genuinely has no Core chase. A product whose
price, pack-count or card inputs were insufficient to evaluate the Core basket
at all has NO Core K: score ``None``, status ``unavailable_*``, and it must not
enter a canonical V11 ranking. Converting the second case into the first would
manufacture a defensible-looking score out of absent data, and would let a
product with unknown chase economics outrank one that was actually measured.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.desirability.chase_core_k import (
    CORE_K_TIER_CONTRACT,
    CORE_MULTIPLE,
)

#: The production Chase Opportunity identity. Names the input (Core K only),
#: the transform family, the numerator and the saturation constant, so a stored
#: score can never be read without the rule that produced it.
CHASE_OPPORTUNITY_V1_VERSION = "chase_opportunity_v1_core_k_saturating_100_k10"

#: Numerator of the saturating transform.
CHASE_OPPORTUNITY_NUMERATOR = 100.0

#: Denominator offset. K == this value yields exactly half the numerator.
CHASE_OPPORTUNITY_SATURATION = 10.0

#: Rounding applied to the public score, matching the Overall/Financial RIP
#: convention in ``weighted_rip``.
CHASE_OPPORTUNITY_PRECISION = 4

#: Why a product can fail to receive a Chase Opportunity score. A product
#: either scores or carries one of these - nothing is dropped silently, and
#: none of these is ever rendered as ``K = 0``.
CHASE_OPPORTUNITY_UNAVAILABLE_REASONS = {
    "unavailable_missing_core_k":
        "Core K was not computed for this product, so the Core chase basket was "
        "never evaluated. This is NOT the same as a Core basket that admitted no "
        "card, which is a valid K = 0.",
    "unavailable_invalid_core_k":
        "Core K was present but is not a finite non-negative integer count.",
}


def _unavailable(reason: str, *, detail: Optional[str] = None) -> Dict[str, Any]:
    return {
        "score": None,
        "coreK": None,
        "version": CHASE_OPPORTUNITY_V1_VERSION,
        "status": reason,
        "statusReason": detail or CHASE_OPPORTUNITY_UNAVAILABLE_REASONS[reason],
        "formula": "100 * core_k / (core_k + 10)",
        "tierContract": CORE_K_TIER_CONTRACT,
        "rankable": False,
    }


def chase_opportunity_score(core_k: Any) -> Optional[float]:
    """The bare transform. ``None`` for any input that is not a valid count.

    Kept separate from :func:`compute_chase_opportunity` so tests and parity
    harnesses can exercise the arithmetic without building a payload.
    """
    try:
        k = float(core_k)
    except (TypeError, ValueError):
        return None
    if k != k or k in (float("inf"), float("-inf")) or k < 0.0:
        return None
    return CHASE_OPPORTUNITY_NUMERATOR * k / (k + CHASE_OPPORTUNITY_SATURATION)


def compute_chase_opportunity(core_k: Any) -> Dict[str, Any]:
    """Chase Opportunity payload for one product.

    ``core_k`` is the Stage V-C Core chase count - the number of cards in the
    product's roster whose value clears ``CORE_MULTIPLE`` times that product's
    own pack-equivalent cost. Pass ``None`` when the Core basket could not be
    evaluated; do NOT pass ``0`` in that case.
    """
    if core_k is None:
        return _unavailable("unavailable_missing_core_k")

    raw = chase_opportunity_score(core_k)
    if raw is None:
        return _unavailable(
            "unavailable_invalid_core_k",
            detail=(
                CHASE_OPPORTUNITY_UNAVAILABLE_REASONS["unavailable_invalid_core_k"]
                + f" Received: {core_k!r}."
            ),
        )

    k_int = int(round(float(core_k)))
    return {
        "score": round(raw, CHASE_OPPORTUNITY_PRECISION),
        "coreK": k_int,
        "version": CHASE_OPPORTUNITY_V1_VERSION,
        "status": "ready",
        "statusReason": None,
        "formula": "100 * core_k / (core_k + 10)",
        "tierContract": CORE_K_TIER_CONTRACT,
        "coreMultiple": CORE_MULTIPLE,
        "rankable": True,
    }
