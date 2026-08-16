"""The sealed-product COMPARISON SCOPE contract.

WHAT THIS ANSWERS
-----------------
Given two sealed-product scores, may they be placed on the same ranking?

Exactly one answer is currently validated:

    booster_box       vs booster_box        ALLOWED
    booster_bundle    vs booster_bundle     ALLOWED
    sleeved_booster_pack vs sleeved_booster_pack  ALLOWED

    booster_box vs booster_bundle           NOT VALIDATED -> NOT ALLOWED
    booster_box vs sleeved_booster_pack     NOT VALIDATED -> NOT ALLOWED
    booster_bundle vs sleeved_booster_pack  NOT VALIDATED -> NOT ALLOWED
    one all-products leaderboard            NOT VALIDATED -> NOT ALLOWED

WHY
---
Stage 1.5 ran controlled pack-count experiments against the SAME set. Financial
RIP V3 was healthy within a family, but score movement across pack counts was
not a constant offset: it varied by set and by chase concentration. That is a
measured property of the score, not a suspicion, and it means a cross-format
ordering would be reporting a modelling artefact as a ranking.

WHAT THIS IS NOT
----------------
NOT a restatement of ``financial_rip_v3_rankable``. That flag answers a
different question - "did the Financial RIP V3 calculation itself produce a
valid, usable score?" - and is a property of ONE score. Comparison scope is a
property of the RELATION between two scores. A perfectly rankable Financial RIP
V3 score for a booster box is still not comparable to a perfectly rankable one
for a bundle. The two must never be collapsed into one flag, in either
direction.

NOT PERSISTED, ON PURPOSE
-------------------------
There is no column for this and no migration adds one. The scope is a versioned
invariant of the CURRENT sealed-product scoring contract: it is identical for
every row ever written under it, so a column would store the same literal on
every row while creating a second place for the policy to be true or false. Read
and publication layers obtain it from this module. If a future contract ever
makes scope vary per row - a validated cross-format calibration, say - THAT is
when a stored column starts carrying information, and it should arrive with the
contract that makes it vary.
"""

from __future__ import annotations

from typing import Any, Dict

from backend.domain.pokemon.sealed_product_composition import SUPPORTED_STAGE1_FAMILIES
from backend.domain.pokemon.sealed_product_stage2_composition import STAGE2_FAMILIES

#: Every family that has a validated WITHIN-family comparison. Stage 2 widens the
#: set of comparable families; it does NOT widen the policy. An Elite Trainer Box
#: may be ranked against another Elite Trainer Box for exactly the reason a
#: Booster Box may be ranked against another Booster Box - same composition, same
#: pack count, same guaranteed-component structure, so the only thing that
#: differs is what is being measured. Nothing here makes an ETB comparable to a
#: Pokemon Center ETB (different pack count AND different guaranteed contents),
#: to a booster box, or to a bundle.
COMPARABLE_FAMILIES = frozenset(SUPPORTED_STAGE1_FAMILIES) | frozenset(STAGE2_FAMILIES)

#: Version of the comparison-scope POLICY itself, so a stored/published payload
#: can be attributed to the rule that produced it.
SEALED_PRODUCT_COMPARISON_SCOPE_VERSION = "sealed-product-comparison-scope-v1"

#: THE single source of truth. Nothing else in the repository may declare a
#: sealed-product comparison scope.
SEALED_PRODUCT_COMPARISON_SCOPE = "within_product_family_only"

#: Deliberately False. "Not validated" and "not allowed" are the same operational
#: answer here: an unvalidated comparison that is nonetheless rendered IS the
#: claim it was never validated for.
SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE = False

SEALED_PRODUCT_COMPARISON_SCOPE_REASON = (
    "Stage 1.5 controlled experiments found pack-count-dependent Financial RIP V3 "
    "score movement that varies by set and chase concentration. Within-family "
    "comparison is validated; cross-format comparison is not."
)


def sealed_product_comparison_scope_contract() -> Dict[str, Any]:
    """The JSON-safe contract every Stage 1 read/summary surface exposes."""
    return {
        "comparisonScope": SEALED_PRODUCT_COMPARISON_SCOPE,
        "crossFormatComparable": SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE,
        "comparisonScopeVersion": SEALED_PRODUCT_COMPARISON_SCOPE_VERSION,
        "comparisonScopeReason": SEALED_PRODUCT_COMPARISON_SCOPE_REASON,
        "comparableFamilies": sorted(COMPARABLE_FAMILIES),
    }


def may_compare_products(left_family: Any, right_family: Any) -> bool:
    """Whether two classified families may appear on one ranking.

    Only identical, SUPPORTED families compare. An unsupported family compares
    with nothing, including itself: Stage 1 has no composition for it, so there
    is no Stage 1 score to compare in the first place.
    """
    left = str(left_family or "").strip()
    right = str(right_family or "").strip()
    if left not in COMPARABLE_FAMILIES or right not in COMPARABLE_FAMILIES:
        return False
    if left == right:
        return True
    return SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE
