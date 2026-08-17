"""Stage 1 sealed-product composition contract.

WHAT THIS IS
------------
The single source of truth for how many loose booster packs a supported Stage 1
sealed product contains, and nothing else. It answers exactly one question:

    given an ALREADY-CLASSIFIED product family, how many same-set booster packs
    does opening this product produce?

WHAT THIS DELIBERATELY IS NOT
-----------------------------
* Not a classifier. Family identity comes from
  ``backend.domain.pokemon.sealed_product_classifier.classify_sealed_product``
  and is consumed here as an input. There is exactly one classifier in the
  repository and this module is not a second one.
* Not a promo/guaranteed-card model. Stage 1 supports only homogeneous same-set
  pack products with no modeled guaranteed card component. Products whose value
  depends on a guaranteed card (enhanced booster boxes, ETBs, UPCs, blister
  promos) are UNSUPPORTED here on purpose - returning a pack count for them
  would silently publish a wrong opening model. They belong to Stage 2, which
  extends this module rather than editing the Stage 1 rows.
* Not a general composition database. Five explicit rows are the whole
  contract; the seam for Stage 2 is a new resolver entry, not a schema.

Anything outside the exact Stage 1 family set resolves to ``None`` - never to a
guess, never to a default of 1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

STAGE1_COMPOSITION_VERSION = "sealed-product-composition-stage1-v2"

#: The only source-set mode Stage 1 models: every pack in the product comes from
#: the same set the pack simulation ran for. Mixed-set products are out of scope.
SOURCE_SET_MODE_SAME_SET = "same_set"


@dataclass(frozen=True)
class Stage1ProductComposition:
    """How one supported Stage 1 sealed product decomposes into booster packs."""

    product_family: str
    pack_count: int
    source_set_mode: str = SOURCE_SET_MODE_SAME_SET
    #: Empty for every Stage 1 row by definition. Present as an explicit field so
    #: Stage 2 has somewhere to put guaranteed promos without changing the shape.
    guaranteed_card_components: Tuple[Any, ...] = field(default_factory=tuple)
    composition_version: str = STAGE1_COMPOSITION_VERSION

    def as_payload(self) -> Dict[str, Any]:
        """JSON-safe disclosure of the composition this result was built on."""
        return {
            "productFamily": self.product_family,
            "packCount": int(self.pack_count),
            "sourceSetMode": self.source_set_mode,
            "guaranteedCardComponents": list(self.guaranteed_card_components),
            "compositionVersion": self.composition_version,
        }


_STAGE1_COMPOSITIONS: Dict[str, Stage1ProductComposition] = {
    "loose_booster_pack": Stage1ProductComposition("loose_booster_pack", 1),
    "sleeved_booster_pack": Stage1ProductComposition("sleeved_booster_pack", 1),
    "booster_bundle": Stage1ProductComposition("booster_bundle", 6),
    # STANDARD booster box only. `enhanced_booster_box` is a separate family in
    # the canonical classifier and is intentionally absent from this map.
    "booster_box": Stage1ProductComposition("booster_box", 36),
    # European half booster boxes are a definitionally uniform retail format:
    # 18 homogeneous same-set packs and no separately modeled contents. They
    # remain a distinct family so 18- and 36-pack products are never compared
    # under one misleading within-family label.
    "half_booster_box": Stage1ProductComposition("half_booster_box", 18),
}

SUPPORTED_STAGE1_FAMILIES = frozenset(_STAGE1_COMPOSITIONS)


def resolve_stage1_composition(product_family: Any) -> Optional[Stage1ProductComposition]:
    """The Stage 1 composition for a classified family, or ``None``.

    ``None`` means "Stage 1 does not model this product", which is a supported,
    expected answer for most sealed products - not an error and not a reason to
    fall back to a pack count.
    """
    key = str(product_family or "").strip()
    return _STAGE1_COMPOSITIONS.get(key)


def is_stage1_supported_family(product_family: Any) -> bool:
    return resolve_stage1_composition(product_family) is not None


# ---------------------------------------------------------------------------
# Composition integrity
# ---------------------------------------------------------------------------
# The canonical classifier resolves IDENTITY ("this is a booster box"), which is
# what it is for and what the market snapshot needs. It does not resolve
# QUANTITY, and real catalogue rows exist whose family is right while their pack
# count is not the Stage 1 default:
#
#     "<Set> Quarter Booster Box"                       -> booster_box, non-default
#     "<Set> Booster Bundle + Surprise Box (Sam's Club)" -> booster_bundle, 6 packs
#                                                           PLUS other product
#
# Both would otherwise be scored at a default pack count against a price that buys
# something else. Stage 1 has no researched composition for either, so it refuses
# them rather than publishing a confident wrong number. These are DISQUALIFIERS,
# not a classifier: they never assign a family and never change one, they only
# say "this SKU's pack count is not the Stage 1 default". Supporting another
# homogeneous format requires a verified canonical composition; extra modeled
# components require an exact Stage 2 composition.

COMPOSITION_INTEGRITY_VERSION = "stage1-composition-integrity-v2"

REASON_NON_DEFAULT_PACK_COUNT = "non_default_pack_count_variant"
REASON_COMPOSITE_PRODUCT = "composite_multi_product_sku"

#: Quantity qualifiers: the family is right, the pack count is not the default.
_NON_DEFAULT_QUANTITY_PATTERNS = (
    r"\bhalf\b",
    r"\bquarter\b",
    r"\bmini\b",
    r"\b\d+\s*[-\s]?pack\b",
)

#: Composite qualifiers: the SKU's price also buys something outside the packs.
_COMPOSITE_PATTERNS = (
    r"\+",
    r"\bwith\b",
    r"\bsurprise box\b",
    r"\bcombo\b",
)


def stage1_composition_disqualifier(product_name: Any, *, product_family: Any = None) -> Optional[str]:
    """Why this SKU cannot use the Stage 1 default pack count, or ``None``.

    Returns a machine-readable reason string. ``None`` means the SKU is an
    ordinary member of its family and the Stage 1 composition applies.
    """
    text = re.sub(r"\s+", " ", str(product_name or "")).strip().lower()
    if not text:
        return None

    family = str(product_family or "").strip()
    for pattern in _NON_DEFAULT_QUANTITY_PATTERNS:
        # A canonical half booster box is definitionally the verified 18-pack
        # family, so "half" is its identity rather than a quantity override.
        if family == "half_booster_box" and pattern == r"\bhalf\b":
            continue
        # A sleeved booster pack IS a single pack; "pack" in its own name is its
        # identity, not a quantity qualifier.
        if family in {"loose_booster_pack", "sleeved_booster_pack"} and pattern == r"\b\d+\s*[-\s]?pack\b":
            continue
        if re.search(pattern, text):
            return REASON_NON_DEFAULT_PACK_COUNT

    for pattern in _COMPOSITE_PATTERNS:
        if re.search(pattern, text):
            return REASON_COMPOSITE_PRODUCT

    return None
