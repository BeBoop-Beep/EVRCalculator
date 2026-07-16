"""Product-support classification: is this product inside the RIP model at all?

This module answers ONE question, from set metadata alone:

    Is this set a booster product the Collector Appeal model is designed to
    score, or is it a fixed-contents product that the model was never built for?

WHY THIS EXISTS (the defect it replaces)
----------------------------------------
The previous ``build_metric_status`` inferred unavailability from the *outcome*
of scoring: a set with ``hit_eligible_card_count == 0`` was labelled
``unavailable_missing_rarity`` - i.e. "this set's data is broken". For all 36
affected sets in production that diagnosis is wrong. Their rarity mapping is
fine and their subject links resolve (every one has ``unique_subject_count > 0``,
e.g. SWSH Black Star Promos links 151 distinct subjects across 304 cards). They
have no hit-eligible cards because **they have no booster pack**: a McDonald's
Collection or an EX Trainer Kit has fixed contents and no pull structure, so
there is nothing for a hit-rarity bucket to classify.

"Missing rarity" invites someone to go fix a rarity mapping that is not broken.
"Unsupported product type" tells the truth: the model does not cover this
product, and no amount of data repair will change that.

THE CENTRAL RULE
----------------
Classification is driven by **set metadata only** (canonical key, name, series).
It deliberately does NOT look at hit counts, card counts, subject counts, or any
scoring output. Inferring "unsupported product" from a zero score would be
circular - it would make the classifier agree with the scorer by construction,
and it would silently reclassify a genuinely broken booster set as "out of
model" the moment its data regressed. A booster set with broken data must stay
loudly broken.

Consequently the two failure families never blur into each other:

    unsupported_*   -> "This product type is outside the RIP model."
                       Correct, permanent, not a bug, nobody should fix it.

    unavailable_*   -> "This should be supported, but its data is incomplete."
                       A defect, actionable, someone should fix it.

VALIDATION AGAINST PRODUCTION (2026-07-15, 171 sets)
-----------------------------------------------------
The rules below partition the catalogue exactly, with no overlap:

    booster (supported)     135 sets   135 score > 0    0 score 0.0
    promo                     8 sets     0 score > 0    8 score 0.0
    mcdonalds                10 sets     0 score > 0   10 score 0.0
    pop_series                9 sets     0 score > 0    9 score 0.0
    trainer_kit               4 sets     0 score > 0    4 score 0.0
    fixed_product             5 sets     0 score > 0    5 score 0.0

Every unsupported set scores 0.0 and every supported set scores above 0.0. The
classifier reproduces the affected cohort exactly without consulting the score,
which is the evidence that product type - not data quality - is the cause.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional

PRODUCT_SUPPORT_VERSION = "product_support_v1"

# --- product_support_type codes -------------------------------------------

VALID_BOOSTER_SET = "valid_booster_set"
PARTIAL_BOOSTER_SET = "partial_booster_set"

UNSUPPORTED_PROMO_PRODUCT = "unsupported_promo_product"
UNSUPPORTED_TRAINER_KIT = "unsupported_trainer_kit"
UNSUPPORTED_MCDONALDS_COLLECTION = "unsupported_mcdonalds_collection"
UNSUPPORTED_POP_SERIES = "unsupported_pop_series"
UNSUPPORTED_FIXED_PRODUCT = "unsupported_fixed_product"

UNSUPPORTED_TYPES = frozenset(
    {
        UNSUPPORTED_PROMO_PRODUCT,
        UNSUPPORTED_TRAINER_KIT,
        UNSUPPORTED_MCDONALDS_COLLECTION,
        UNSUPPORTED_POP_SERIES,
        UNSUPPORTED_FIXED_PRODUCT,
    }
)

# --- Fixed-contents products with no shared naming pattern -----------------
#
# These five have nothing in their key to match on, so they are pinned
# explicitly. An explicit registry is preferable to a loose pattern here: a
# fuzzy rule broad enough to catch "Best of Game" would risk swallowing real
# booster sets. Each entry is a deliberate, reviewable decision.
FIXED_PRODUCT_KEYS: Dict[str, str] = {
    "bestofgame": "Fixed 9-card promotional insert set; no booster pack.",
    "kalosstarterset": "Fixed-contents starter product; no booster pull structure.",
    "pokmonfutsalcollection": "Fixed 5-card promotional collection; no booster pack.",
    "pokmonrumble": "Fixed-contents video-game tie-in product; no booster pack.",
    "southernislands": "Fixed 18-card collector set sold complete; no booster pack.",
}

# --- Pattern rules ---------------------------------------------------------
#
# Ordered; first match wins. Each pattern targets a product FAMILY whose
# defining trait is fixed or non-booster distribution.
_PATTERN_RULES = (
    (
        re.compile(r"blackstarpromo", re.IGNORECASE),
        UNSUPPORTED_PROMO_PRODUCT,
        "promo",
        "Black Star Promos are a distribution channel, not a sealed booster product: "
        "cards arrive via tins, blisters and events, so there is no pack to open and "
        "no pull structure to model.",
    ),
    (
        re.compile(r"trainerkit", re.IGNORECASE),
        UNSUPPORTED_TRAINER_KIT,
        "trainer_kit",
        "Trainer Kits ship two fixed preconstructed decks. Contents are identical in "
        "every copy, so there is nothing to pull and no chase structure.",
    ),
    (
        re.compile(r"^mcdonald", re.IGNORECASE),
        UNSUPPORTED_MCDONALDS_COLLECTION,
        "mcdonalds",
        "McDonald's Collections are fixed 4-card promotional packs from a small shared "
        "checklist; they have no booster rarity ladder and no elite chase.",
    ),
    (
        re.compile(r"^popseries", re.IGNORECASE),
        UNSUPPORTED_POP_SERIES,
        "pop_series",
        "POP Series were Organized Play league distributions, not retail boosters; "
        "there is no purchasable pack whose contents can be simulated.",
    ),
)


def _normalize(value: Any) -> str:
    """Canonical keys are camelCase; comparison is lowercase and punctuation-free."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def classify_product_support(
    *,
    set_canonical_key: Any,
    set_name: Any = None,
    set_series: Any = None,
) -> Dict[str, Any]:
    """Classify a set's product support from metadata alone.

    Never reads scores, hit counts or card counts - see the module docstring on
    why inferring support from the score would be circular.

    Returns ``supported=True`` for anything not positively identified as a
    non-booster product. Defaulting to *supported* is deliberate: an unknown new
    set should be treated as a booster set and surface real data defects loudly,
    rather than be silently excluded from the model by a classifier that has
    simply never heard of it.
    """
    key = _normalize(set_canonical_key)
    name = _normalize(set_name)

    fixed_reason = FIXED_PRODUCT_KEYS.get(key)
    if fixed_reason is not None:
        return _unsupported(
            product_support_type=UNSUPPORTED_FIXED_PRODUCT,
            product_family="fixed_product",
            reason=fixed_reason,
            matched_on="canonical_key_registry",
            matched_value=str(set_canonical_key or ""),
        )

    for pattern, support_type, family, reason in _PATTERN_RULES:
        for source, value in (("canonical_key", key), ("set_name", name)):
            if value and pattern.search(value):
                return _unsupported(
                    product_support_type=support_type,
                    product_family=family,
                    reason=reason,
                    matched_on=f"{source}_pattern",
                    matched_value=pattern.pattern,
                )

    return {
        "product_support_type": VALID_BOOSTER_SET,
        "product_family": "booster",
        "supported": True,
        "product_support_reason": None,
        "matched_on": "default_supported",
        "matched_value": None,
        "product_support_version": PRODUCT_SUPPORT_VERSION,
        "set_series": str(set_series) if set_series else None,
    }


def _unsupported(
    *,
    product_support_type: str,
    product_family: str,
    reason: str,
    matched_on: str,
    matched_value: str,
) -> Dict[str, Any]:
    return {
        "product_support_type": product_support_type,
        "product_family": product_family,
        "supported": False,
        "product_support_reason": reason,
        "matched_on": matched_on,
        "matched_value": matched_value,
        "product_support_version": PRODUCT_SUPPORT_VERSION,
    }


def is_supported_product(set_row: Mapping[str, Any]) -> bool:
    """Convenience predicate over a set row carrying canonical key / name."""
    return bool(
        classify_product_support(
            set_canonical_key=set_row.get("canonical_key") or set_row.get("set_canonical_key"),
            set_name=set_row.get("name") or set_row.get("set_name"),
            set_series=set_row.get("series") or set_row.get("set_series"),
        )["supported"]
    )
