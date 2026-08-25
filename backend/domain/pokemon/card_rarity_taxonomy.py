"""Canonical card-rarity taxonomy for Market card submarkets.

WHY THIS EXISTS. `pokemon_canonical_cards.rarity` is a free-text field sourced
from the Pokémon TCG API, and the tracked universe genuinely carries the same
rarity under several spellings — "Rare" and "rare", "Double Rare" and
"double rare", "MEGA_ATTACK_RARE" in screaming snake case. A second authority,
`pokemon_set_top_chase_card_daily_history`, stores the same concepts entirely
lowercased. Grouping on the raw display string would therefore split one rarity
into two markets.

WHAT IT DOES. Exactly two things:

  1. Normalizes a raw rarity string to a canonical key, by EXACT match on a
     case- and separator-folded form.
  2. Declares which canonical keys are published as market segments.

WHAT IT DOES NOT DO. It does not guess. Normalization is exact-match only,
never substring: "Mega Hyper Rare" and "Shiny Ultra Rare" are their own
rarities and must not be folded into "Hyper Rare" or "Ultra Rare" by a
`in`-test. Anything unrecognised stays unrecognised and lands in the residual
rather than being forced into a neighbouring segment.

ERA SCOPE. Published segments span BOTH the modern (Scarlet & Violet) rarity
system and the pre-Scarlet & Violet one, because Market Explorer's era filter
makes a legacy rarity a genuinely selectable market ("Sword & Shield · Rare
Ultra") rather than dead weight in a global list. Crucially, the two systems
are never merged: "Rare Ultra" and "Ultra Rare" are different eras' products
with different price regimes and stay separate canonical keys. A rarity that is
too thin, or belongs to neither system cleanly, still lands in the residual —
nothing is forced into a neighbouring segment to make the filter look complete.

VERSIONING. `CARD_RARITY_TAXONOMY_VERSION` is published with every payload. A
future normalization correction changes this string, so a membership definition
can never change silently.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

CARD_RARITY_TAXONOMY_VERSION = "pokemon-card-rarity-taxonomy-v2"

#: Least-arbitrary quality gate, chosen from the observed distribution of the
#: tracked universe (167 sets, audited 2026-08-24) rather than picked round.
#: Priced-card counts of the hit rarities fall 768, 492, 356, 324, 319, 317,
#: 222, 149, 120, 110, 80, 74, then 55, 43, 35, 27… — and the represented-set
#: counts fall 62, 30, 22, 21, 14, then 6, 5, 2, 1. The 25-card / 3-set
#: thresholds sit inside those gaps rather than on a boundary, so no segment's
#: inclusion is decided by the threshold itself. Two rarities are excluded by
#: the SET dimension alone despite ample card counts — Rare Shiny (149 cards,
#: 2 sets) and Shiny Rare (120 cards, 1 set) — which is the gate working as
#: intended: those are a set's mechanic, not a cross-market rarity.
MIN_SEGMENT_CARD_COUNT = 25
MIN_SEGMENT_SET_COUNT = 3


def _fold(value: Any) -> str:
    """Case- and separator-folded comparison form. Never a fuzzy match."""
    text = str(value or "").strip().lower()
    text = text.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text)


#: Folded raw value -> canonical rarity key. EXACT match only.
#:
#: Every alias here was observed in production data. Adding an alias is a
#: taxonomy change and must come with a version bump.
RARITY_ALIASES: dict[str, str] = {
    "special illustration rare": "specialIllustrationRare",
    "illustration rare": "illustrationRare",
    "ultra rare": "ultraRare",
    "hyper rare": "hyperRare",
    "double rare": "doubleRare",
    "rare": "rare",
    "common": "common",
    "uncommon": "uncommon",
    "promo": "promo",
    "ace spec rare": "aceSpecRare",
    # Pre-Scarlet & Violet hit rarities. The Pokemon TCG API spells the older
    # eras' rarities with the qualifier LAST ("Rare Ultra", "Rare Secret")
    # where the modern era puts it first ("Ultra Rare"). These are kept as
    # SEPARATE canonical keys rather than folded into their modern-sounding
    # counterparts: "Rare Ultra" is a Sword & Shield-and-earlier product with
    # its own price regime and its own supply, and merging it into "Ultra
    # Rare" would produce a segment whose movements are two different markets
    # averaged together.
    "rare ultra": "rareUltra",
    "rare secret": "rareSecret",
    "rare rainbow": "rareRainbow",
    "rare holo": "rareHolo",
    # Deliberately DISTINCT keys. These read like modifiers of the rarities
    # above but are separate products with their own price levels, and folding
    # them in would move a segment for reasons that are not that segment moving.
    "shiny rare": "shinyRare",
    "shiny ultra rare": "shinyUltraRare",
    "mega hyper rare": "megaHyperRare",
    "mega attack rare": "megaAttackRare",
    "black white rare": "blackWhiteRare",
}


def normalize_rarity(value: Any) -> str | None:
    """Canonical rarity key for a raw rarity string, or None when unknown.

    None means "this rarity is not part of the taxonomy" — it belongs to the
    parent market and to the residual, never to a published segment.
    """
    folded = _fold(value)
    if not folded:
        return None
    return RARITY_ALIASES.get(folded)


#: Ordered published Raw Card submarkets. `rarityKeys` are canonical keys, not
#: raw strings. Every segment here cleared the quality gate against the tracked
#: universe; the counts that justified each are asserted by the audit tests.
RAW_CARD_SEGMENT_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "specialIllustrationRare",
        "label": "Special Illustration Rare",
        "rarityKeys": ("specialIllustrationRare",),
        "definition": "Canonical cards classified as Special Illustration Rare across eligible tracked sets.",
    },
    {
        "key": "illustrationRare",
        "label": "Illustration Rare",
        "rarityKeys": ("illustrationRare",),
        "definition": "Canonical cards classified as Illustration Rare across eligible tracked sets.",
    },
    {
        "key": "ultraRare",
        "label": "Ultra Rare",
        "rarityKeys": ("ultraRare",),
        "definition": "Canonical cards classified as Ultra Rare. Shiny Ultra Rare is a separate rarity and is not counted here.",
    },
    {
        "key": "hyperRare",
        "label": "Hyper Rare",
        "rarityKeys": ("hyperRare",),
        "definition": "Canonical cards classified as Hyper Rare. Mega Hyper Rare is a separate rarity and is not counted here.",
    },
    {
        "key": "doubleRare",
        "label": "Double Rare",
        "rarityKeys": ("doubleRare",),
        "definition": "Canonical cards classified as Double Rare across eligible tracked sets.",
    },
    {
        "key": "rareUltra",
        "label": "Rare Ultra",
        "rarityKeys": ("rareUltra",),
        "definition": "Pre-Scarlet & Violet ultra rares, spelled \"Rare Ultra\" by the source catalogue. A separate rarity from the modern Ultra Rare, not a spelling of it.",
    },
    {
        "key": "rareSecret",
        "label": "Rare Secret",
        "rarityKeys": ("rareSecret",),
        "definition": "Pre-Scarlet & Violet secret rares across eligible tracked sets.",
    },
    {
        "key": "rareRainbow",
        "label": "Rare Rainbow",
        "rarityKeys": ("rareRainbow",),
        "definition": "Rainbow rares, concentrated in the Sun & Moon and Sword & Shield eras.",
    },
    {
        "key": "rareHolo",
        "label": "Rare Holo",
        "rarityKeys": ("rareHolo",),
        "definition": "Classic holographic rares. The broadest legacy segment, spanning most pre-Scarlet & Violet sets.",
    },
)

RESIDUAL_CARD_SEGMENT_KEY = "otherCards"
RESIDUAL_CARD_SEGMENT_LABEL = "Other Cards"


def segment_key_for_rarity(raw_rarity: Any) -> str | None:
    """Published segment for a raw rarity string, or None for the residual."""
    canonical = normalize_rarity(raw_rarity)
    if canonical is None:
        return None
    for definition in RAW_CARD_SEGMENT_DEFINITIONS:
        if canonical in definition["rarityKeys"]:
            return str(definition["key"])
    return None


def partition_cards_by_segment(
    cards: Iterable[Mapping[str, Any]], *, rarity_field: str = "rarity",
) -> dict[str, list[dict[str, Any]]]:
    """Group cards into published rarity segments plus the residual.

    Always returns a key for EVERY published segment, so "this segment has no
    constituents" is distinguishable from "this segment does not exist".
    """
    grouped: dict[str, list[dict[str, Any]]] = {
        str(definition["key"]): [] for definition in RAW_CARD_SEGMENT_DEFINITIONS
    }
    grouped[RESIDUAL_CARD_SEGMENT_KEY] = []
    for card in cards:
        key = segment_key_for_rarity(card.get(rarity_field))
        grouped[key if key is not None else RESIDUAL_CARD_SEGMENT_KEY].append(dict(card))
    return grouped


def meets_quality_gate(*, card_count: int, set_count: int) -> bool:
    """Whether a rarity universe is large and broad enough to publish.

    A market index over a handful of cards from one set is not a market — it is
    those cards. Both dimensions matter: Shiny Rare has 120 tracked cards but
    they all live in ONE set, which makes it that set's mechanic rather than a
    cross-market rarity segment.
    """
    return int(card_count) >= MIN_SEGMENT_CARD_COUNT and int(set_count) >= MIN_SEGMENT_SET_COUNT


def taxonomy_metadata() -> dict[str, Any]:
    """The published, self-describing definition of this segmentation."""
    return {
        "taxonomyVersion": CARD_RARITY_TAXONOMY_VERSION,
        "parentMarket": "raw",
        "segments": [
            {
                "key": definition["key"],
                "label": definition["label"],
                "rarityKeys": list(definition["rarityKeys"]),
                "definition": definition["definition"],
            }
            for definition in RAW_CARD_SEGMENT_DEFINITIONS
        ],
        "residual": {
            "key": RESIDUAL_CARD_SEGMENT_KEY,
            "label": RESIDUAL_CARD_SEGMENT_LABEL,
            "definition": (
                "Tracked cards whose rarity is not published as its own submarket — "
                "base rarities, era-specific rarities and rarities too thinly represented "
                "to support an index."
            ),
        },
        "qualityGate": {
            "minCardCount": MIN_SEGMENT_CARD_COUNT,
            "minSetCount": MIN_SEGMENT_SET_COUNT,
        },
        "disjoint": True,
        "reconciliation": (
            "Published rarity segment Tracked Values plus the residual reconcile to the "
            "Raw Card Market Tracked Value; every tracked card belongs to exactly one bucket."
        ),
    }
