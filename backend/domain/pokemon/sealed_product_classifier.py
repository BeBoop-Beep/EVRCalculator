"""Deterministic identity classification for raw sealed-product names."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

CLASSIFICATION_VERSION = "sealed-product-classification-v3-loose-pack-family"
OVERVIEW_FAMILIES = frozenset(
    {
        "booster_box",
        "half_booster_box",
        "enhanced_booster_box",
        "elite_trainer_box",
        "pokemon_center_elite_trainer_box",
        "booster_bundle",
        "loose_booster_pack",
        "sleeved_booster_pack",
    }
)

FAMILY_LABELS = {
    "booster_box": "Booster Box",
    "half_booster_box": "Half Booster Box",
    "enhanced_booster_box": "Enhanced Booster Box",
    "elite_trainer_box": "Elite Trainer Box",
    "pokemon_center_elite_trainer_box": "Pokémon Center Elite Trainer Box",
    "booster_bundle": "Booster Bundle",
    "loose_booster_pack": "Loose Booster Pack",
    "sleeved_booster_pack": "Sleeved Booster Pack",
    "build_and_battle_box": "Build & Battle Box",
    "build_and_battle_stadium": "Build & Battle Stadium",
    "three_pack_blister": "Three-Pack Blister",
    "single_pack_blister": "Single-Pack Blister",
    "collection_product": "Collection Product",
    "case": "Case",
    "display": "Display",
    "multi_product_bundle": "Multi-Product Bundle",
    "fun_pack": "Fun Pack",
    "other": "Other",
}


def _variant(name: str) -> Optional[str]:
    matches = re.findall(r"\[([^\]]+)\]", name)
    return matches[-1].strip() if matches else None


def classify_sealed_product(name: Any) -> Dict[str, Any]:
    raw = str(name or "").strip()
    text = re.sub(r"\s+", " ", raw).lower()
    is_case = bool(re.search(r"\bcase\b", text))
    is_display = bool(re.search(r"\bdisplay\b", text))
    set_listing = bool(re.search(r"\bset of\s+\d+\b", text))

    # Precedence is intentional: container/listing identities before their
    # contained retail product, and specific retail products before generic.
    if is_case:
        family = "case"
    elif is_display:
        family = "display"
    elif set_listing or ("art bundle" in text):
        family = "multi_product_bundle"
    elif "pokemon center elite trainer box" in text or "pokémon center elite trainer box" in text:
        family = "pokemon_center_elite_trainer_box"
    elif "elite trainer box" in text:
        family = "elite_trainer_box"
    elif "enhanced booster box" in text:
        family = "enhanced_booster_box"
    elif "half booster box" in text:
        family = "half_booster_box"
    elif "booster box" in text:
        family = "booster_box"
    elif "build & battle stadium" in text or "build and battle stadium" in text:
        family = "build_and_battle_stadium"
    elif "build & battle box" in text or "build and battle box" in text:
        family = "build_and_battle_box"
    elif "booster bundle" in text:
        family = "booster_bundle"
    elif "sleeved booster pack" in text:
        family = "sleeved_booster_pack"
    elif "three-pack blister" in text or "3 pack blister" in text or "3-pack blister" in text:
        family = "three_pack_blister"
    elif "single-pack blister" in text or "checklane blister" in text:
        family = "single_pack_blister"
    elif "fun pack" in text:
        family = "fun_pack"
    elif "booster pack" in text:
        family = "loose_booster_pack"
    elif re.search(r"\b(bundle|collection|tin|chest|box set)\b", text):
        family = "collection_product"
    else:
        family = "other"

    return {
        "productFamily": family,
        "productFamilyLabel": FAMILY_LABELS[family],
        "variantLabel": _variant(raw),
        "unitQuantity": 1,
        "isCase": is_case,
        "isDisplay": is_display,
        "isMultiProductBundle": family == "multi_product_bundle",
        "isOverviewEligible": family in OVERVIEW_FAMILIES,
        "classificationVersion": CLASSIFICATION_VERSION,
    }
