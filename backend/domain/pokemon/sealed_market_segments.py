"""Sealed Market submarket (product-family) segment definitions.

WHAT THIS IS. The global Sealed Market is one index over every overview-eligible
sealed SKU across every tracked set. This module cuts that SAME constituent
universe into product-family submarkets — Booster Boxes, Elite Trainer Boxes,
Pokémon Center ETBs, Booster Bundles, Packs — so they can be compared against
each other and against their parent.

WHAT THIS IS NOT. It is not a second classifier. Family identity comes from
``sealed_product_classifier.classify_sealed_product``, which the set-level
sealed snapshots already ran and published as ``productFamily`` on every
product. This module only groups those canonical family keys into published
segments; a product's family is never re-decided here.

METHODOLOGY. Each segment is built from its own constituent SKUs by the same
``build_sealed_segment_history`` the parent uses. Segment indexes are never
averaged from other indexes, never derived from Tracked Value percentages, and
never produced by filtering an already-aggregated index.

DISJOINTNESS. Every segment's family set is disjoint from every other's, so a
product belongs to at most one published segment and segment Tracked Values are
additive. In particular Pokémon Center ETBs are their OWN segment and are NOT
counted inside Elite Trainer Boxes — the classifier already resolves PC ETBs
first, and blending them would mix two products with materially different
price levels under one label.

RESIDUAL. Not every overview-eligible family is published as a segment: Half
Booster Boxes and Enhanced Booster Boxes are eligible for the parent but are
not their own market. They are reported as a documented residual
("otherSealed") in segment metadata rather than being folded into Booster Boxes
to manufacture a clean reconciliation. Parent = published segments + residual,
exactly.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from backend.domain.pokemon.sealed_product_classifier import (
    CLASSIFICATION_VERSION,
    OVERVIEW_FAMILIES,
)

SEALED_SEGMENT_CONTRACT_VERSION = "pokemon-sealed-segments-v1"

#: The parent. Published alongside the children under the same collection so a
#: consumer can select "Total Sealed" as one series among the submarkets.
SEALED_SEGMENT_TOTAL_KEY = "total"

#: Ordered published submarkets. ``productFamilies`` are canonical classifier
#: keys; ``isComposite`` marks a segment that deliberately unions more than one
#: family and therefore needs its definition stated in the UI.
SEALED_SEGMENT_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "boosterBox",
        "label": "Booster Boxes",
        "productFamilies": ("booster_box",),
        "isComposite": False,
        # Deliberately strict. Half and Enhanced Booster Boxes are different
        # products at different price levels; unioning them here would move
        # this index for reasons that are not the Booster Box market moving.
        "definition": "Standard sealed Booster Boxes. Half and Enhanced Booster Boxes are excluded.",
    },
    {
        "key": "eliteTrainerBox",
        "label": "Elite Trainer Boxes",
        "productFamilies": ("elite_trainer_box",),
        "isComposite": False,
        "definition": "Standard Elite Trainer Boxes. Pokémon Center ETBs are a separate segment and are not counted here.",
    },
    {
        "key": "pokemonCenterEliteTrainerBox",
        "label": "Pokémon Center ETBs",
        "productFamilies": ("pokemon_center_elite_trainer_box",),
        "isComposite": False,
        "definition": "Pokémon Center exclusive Elite Trainer Boxes only.",
    },
    {
        "key": "boosterBundle",
        "label": "Booster Bundles",
        "productFamilies": ("booster_bundle",),
        "isComposite": False,
        "definition": "Sealed Booster Bundles.",
    },
    {
        "key": "packs",
        "label": "Packs",
        "productFamilies": ("loose_booster_pack", "sleeved_booster_pack"),
        "isComposite": True,
        # STATED COMPOSITE. The backend keeps loose and sleeved as distinct
        # classifier families; this segment unions them because they are the
        # same unit of the market (one booster pack) sold in two wrappers. The
        # union is declared here and asserted by tests, never implied.
        "definition": "Single booster packs — loose booster packs and sleeved booster packs combined.",
    },
)

#: Overview-eligible families that no published segment claims. They still
#: belong to the parent Sealed Market; they are simply not a market of their
#: own. Kept as a computed residual so parent/child reconciliation is exact
#: rather than approximately true.
RESIDUAL_SEGMENT_KEY = "otherSealed"
RESIDUAL_SEGMENT_LABEL = "Other Sealed"


def _published_families() -> frozenset[str]:
    return frozenset(
        family
        for definition in SEALED_SEGMENT_DEFINITIONS
        for family in definition["productFamilies"]
    )


#: Families eligible for the parent but not published as a segment.
RESIDUAL_PRODUCT_FAMILIES: tuple[str, ...] = tuple(
    sorted(OVERVIEW_FAMILIES - _published_families())
)


def segment_key_for_family(product_family: Any) -> str | None:
    """The published segment a canonical family key belongs to, or None.

    None means "eligible for the parent, but not its own published market" —
    the residual — or a family that is not overview-eligible at all.
    """
    key = str(product_family or "").strip()
    for definition in SEALED_SEGMENT_DEFINITIONS:
        if key in definition["productFamilies"]:
            return str(definition["key"])
    return None


def partition_products_by_segment(
    products: Iterable[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group already-classified products into published segments.

    The returned mapping always carries a key for EVERY published segment plus
    the residual, even when empty, so a caller can tell "this segment has no
    constituents today" apart from "this segment does not exist". Products are
    grouped by their published ``productFamily``; nothing is re-classified.
    """
    grouped: dict[str, list[dict[str, Any]]] = {
        str(definition["key"]): [] for definition in SEALED_SEGMENT_DEFINITIONS
    }
    grouped[RESIDUAL_SEGMENT_KEY] = []
    for product in products:
        key = segment_key_for_family(product.get("productFamily"))
        grouped[key if key is not None else RESIDUAL_SEGMENT_KEY].append(dict(product))
    return grouped


def segment_definition_metadata() -> dict[str, Any]:
    """The published, self-describing definition of this segmentation."""
    return {
        "contractVersion": SEALED_SEGMENT_CONTRACT_VERSION,
        "classificationVersion": CLASSIFICATION_VERSION,
        "segments": [
            {
                "key": definition["key"],
                "label": definition["label"],
                "productFamilies": list(definition["productFamilies"]),
                "isComposite": bool(definition["isComposite"]),
                "definition": definition["definition"],
            }
            for definition in SEALED_SEGMENT_DEFINITIONS
        ],
        "residual": {
            "key": RESIDUAL_SEGMENT_KEY,
            "label": RESIDUAL_SEGMENT_LABEL,
            "productFamilies": list(RESIDUAL_PRODUCT_FAMILIES),
            "definition": (
                "Overview-eligible sealed products that belong to the parent Sealed "
                "Market but are not published as their own submarket."
            ),
        },
        "disjoint": True,
        "reconciliation": (
            "Published segment Tracked Values plus the residual reconcile to the "
            "parent Sealed Market Tracked Value; every eligible product belongs to "
            "exactly one bucket."
        ),
    }
