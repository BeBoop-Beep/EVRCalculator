"""Reviewed Pokemon TCG API image sources for historical TCGplayer-only catalogs.

The cold-start catalog baseline added TCGplayer catalogs that have no Pokemon API
set of their own: promo bins, trainer kits, deck/blister exclusives, jumbo cards
and similar. Their authoritative identity is the TCGplayer catalog id stored in
each config as ``TCGPLAYER_SET_ID``, and their pricing comes from that catalog.

Some of them nevertheless contain cards that *also* exist inside a Pokemon API
set, so images can be borrowed from there. This module records those reviewed
borrow relationships and nothing else.

A mapping here is deliberately NOT an identity:

* it never becomes ``SET_ID`` in a set config;
* it never becomes ``sets.pokemon_api_set_id``;
* several entries point at an API set that another local set already owns
  (``expedition`` borrows from ``ecard1``, which ``eCardEra/expeditionBaseSet``
  owns). Writing it as an identity would create duplicate API-set ownership.

Every entry was verified against the live Pokemon TCG API catalog (174 sets) and
against the internal card counts for the catalog. Counts are recorded so drift
shows up in the enrichment dry-run report instead of silently passing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

# The three outcomes a historical catalog can have.
ONE_TO_ONE = "one_to_one_api_match"
PARENT_OR_MULTI = "multi_or_parent_api_mapping_required"
NO_EQUIVALENT = "no_api_equivalent"


@dataclass(frozen=True)
class CatalogImageSource:
    """Where a historical catalog may read card images from. Not an identity."""

    canonical_key: str
    tcgplayer_set_id: str
    tcgplayer_set_name: str
    api_set_ids: Tuple[str, ...]
    match_kind: str
    strategy: str
    evidence: str
    reviewed_internal_card_count: int
    reviewed_api_card_count: int


def _entry(**kwargs) -> CatalogImageSource:
    return CatalogImageSource(**kwargs)


REVIEWED_IMAGE_SOURCES: Dict[str, CatalogImageSource] = {
    # ---------------------------------------------------------------- one-to-one
    "expedition": _entry(
        canonical_key="expedition",
        tcgplayer_set_id="1375",
        tcgplayer_set_name="Expedition",
        api_set_ids=("ecard1",),
        match_kind=ONE_TO_ONE,
        strategy="confirmed_name_alias",
        evidence=(
            "TCGplayer 'Expedition' is the API 'Expedition Base Set'. "
            "Card counts agree exactly (internal 165 / API 165). "
            "ecard1 is already owned by eCardEra/expeditionBaseSet, so this is an "
            "image source only."
        ),
        reviewed_internal_card_count=165,
        reviewed_api_card_count=165,
    ),
    "wotcPromo": _entry(
        canonical_key="wotcPromo",
        tcgplayer_set_id="1418",
        tcgplayer_set_name="WoTC Promo",
        api_set_ids=("basep",),
        match_kind=ONE_TO_ONE,
        strategy="confirmed_name_alias",
        evidence=(
            "TCGplayer 'WoTC Promo' is the API 'Wizards Black Star Promos'. "
            "Internal 69 vs API 53: TCGplayer carries extra printings/variants, so "
            "image coverage is partial by design. basep is owned by "
            "baseWotcEra/wizardsBlackStarPromos."
        ),
        reviewed_internal_card_count=69,
        reviewed_api_card_count=53,
    ),
    "diamondAndPearlPromos": _entry(
        canonical_key="diamondAndPearlPromos",
        tcgplayer_set_id="1421",
        tcgplayer_set_name="Diamond and Pearl Promos",
        api_set_ids=("dpp",),
        match_kind=ONE_TO_ONE,
        strategy="confirmed_name_alias",
        evidence=(
            "TCGplayer 'Diamond and Pearl Promos' is the API 'DP Black Star Promos'. "
            "Internal 60 vs API 56. dpp is owned by diamondAndPearlEra/dpBlackStarPromos."
        ),
        reviewed_internal_card_count=60,
        reviewed_api_card_count=56,
    ),
    "swshSwordAndShieldPromoCards": _entry(
        canonical_key="swshSwordAndShieldPromoCards",
        tcgplayer_set_id="2545",
        tcgplayer_set_name="SWSH: Sword & Shield Promo Cards",
        api_set_ids=("swshp",),
        match_kind=ONE_TO_ONE,
        strategy="confirmed_name_alias",
        evidence=(
            "TCGplayer 'SWSH: Sword & Shield Promo Cards' is the API "
            "'SWSH Black Star Promos'. Internal 341 vs API 304. swshp is owned by "
            "swordAndShieldEra/swshBlackStarPromos."
        ),
        reviewed_internal_card_count=341,
        reviewed_api_card_count=304,
    ),
    "svScarletAndVioletPromoCards": _entry(
        canonical_key="svScarletAndVioletPromoCards",
        tcgplayer_set_id="22872",
        tcgplayer_set_name="SV: Scarlet & Violet Promo Cards",
        api_set_ids=("svp",),
        match_kind=ONE_TO_ONE,
        strategy="era_promo_naming_pattern",
        evidence=(
            "Same '<ERA>: <Era> Promo Cards' -> '<ERA> Black Star Promos' pattern as the "
            "confirmed swshp and dpp mappings; svp is the only Scarlet & Violet promo "
            "set in the API catalog. Internal 280 vs API 196 (TCGplayer carries extra "
            "variants). svp is not owned by any local set."
        ),
        reviewed_internal_card_count=280,
        reviewed_api_card_count=196,
    ),
    "sveScarletAndVioletEnergies": _entry(
        canonical_key="sveScarletAndVioletEnergies",
        tcgplayer_set_id="24382",
        tcgplayer_set_name="SVE: Scarlet & Violet Energies",
        api_set_ids=("sve",),
        match_kind=ONE_TO_ONE,
        strategy="confirmed_name_alias",
        evidence=(
            "TCGplayer 'SVE: Scarlet & Violet Energies' is the API 'Scarlet & Violet "
            "Energies' (sve), the only energy set in the API catalog. Internal 40 vs "
            "API 8: TCGplayer lists many printings of the same 8 energies, so image "
            "coverage is partial by design."
        ),
        reviewed_internal_card_count=40,
        reviewed_api_card_count=8,
    ),
    # ------------------------------------------------------- parent / subset only
    "legendaryTreasuresRadiantCollection": _entry(
        canonical_key="legendaryTreasuresRadiantCollection",
        tcgplayer_set_id="1465",
        tcgplayer_set_name="Legendary Treasures: Radiant Collection",
        api_set_ids=("bw11",),
        match_kind=PARENT_OR_MULTI,
        strategy="parent_set_subset",
        evidence=(
            "The Radiant Collection is the RC1-RC25 subrange printed inside the API "
            "parent set 'Legendary Treasures' (bw11); it has no API set of its own. "
            "Verified live: bw11 returns 140 cards of which exactly 25 are numbered "
            "RC1-RC25, matching the 25 internal cards. Image matching is keyed on card "
            "number, so only the RC range can match. bw11 is owned by "
            "blackAndWhiteEra/legendaryTreasures."
        ),
        reviewed_internal_card_count=25,
        reviewed_api_card_count=140,
    ),
    "generationsRadiantCollection": _entry(
        canonical_key="generationsRadiantCollection",
        tcgplayer_set_id="1729",
        tcgplayer_set_name="Generations: Radiant Collection",
        api_set_ids=("g1",),
        match_kind=PARENT_OR_MULTI,
        strategy="parent_set_subset",
        evidence=(
            "The Radiant Collection is the RC1-RC32 subrange printed inside the API "
            "parent set 'Generations' (g1). Verified live: g1 returns 117 cards of "
            "which exactly 32 are numbered RC1-RC32, matching the 32 internal cards. "
            "g1 is owned by xyEra/generations."
        ),
        reviewed_internal_card_count=32,
        reviewed_api_card_count=117,
    ),
    "baseSetShadowless": _entry(
        canonical_key="baseSetShadowless",
        tcgplayer_set_id="1663",
        tcgplayer_set_name="Base Set (Shadowless)",
        api_set_ids=("base1",),
        match_kind=PARENT_OR_MULTI,
        strategy="print_variant_of_parent",
        evidence=(
            "Shadowless is a print variant of Base Set, not a separate set: the API has "
            "no shadowless set. Internal 102 matches API base1 102 exactly, so images "
            "carry over card-for-card, but the catalog identity stays TCGplayer 1663 "
            "because base1 is owned by baseWotcEra/base."
        ),
        reviewed_internal_card_count=102,
        reviewed_api_card_count=102,
    ),
}


# Catalogs deliberately left unmapped, with the reason surfaced in the dry-run
# report so "no match" is never mistaken for "not looked at yet".
REFUSED_CATALOGS: Dict[str, str] = {
    "battleAcademy": (
        "Mixed catalog: Battle Academy decks reprint cards from multiple source sets; "
        "no single API set covers it."
    ),
    "battleAcademy2022": (
        "Mixed catalog: reprints drawn from multiple API sets across several eras."
    ),
    "battleAcademy2024": (
        "Mixed catalog: reprints drawn from multiple API sets across several eras."
    ),
    "worldChampionshipDecks": (
        "Mixed catalog: 1831 internal cards spanning every era of championship decks; "
        "multiple API sets and many cards with no API equivalent at all."
    ),
    "deckExclusives": (
        "Mixed catalog: 506 internal cards pulled from multiple theme decks across eras."
    ),
    "blisterExclusives": (
        "Mixed catalog: 135 internal cards from multiple blister promos across eras."
    ),
    "alternateArtPromos": (
        "Mixed catalog: alternate-art promos sourced from multiple API sets and "
        "distributions."
    ),
    "firstPartnerPack": (
        "Mixed catalog: First Partner Pack jumbo cards reprint art from multiple "
        "generations; no single API set covers it."
    ),
    "bestOfPromos": (
        "Ambiguous: the only near-name API set is 'Best of Game' (bp, 9 cards), which "
        "otherEra/bestOfGame already owns and which does not match the 15 internal "
        "cards. Needs manual card-level review before any mapping."
    ),
    "tradingCardGameClassic": (
        "Ambiguous: 102 internal cards coincidentally equals Base Set's 102, but "
        "Trading Card Game Classic is a three-deck reprint product spanning several "
        "sets. Needs card-level review."
    ),
}

_BY_PROVIDER_ID: Dict[str, CatalogImageSource] = {
    mapping.tcgplayer_set_id: mapping for mapping in REVIEWED_IMAGE_SOURCES.values()
}


def resolve(
    canonical_key: Optional[str] = None, tcgplayer_set_id: Optional[str] = None
) -> Optional[CatalogImageSource]:
    """Look up a reviewed image source by canonical key or by TCGplayer set id."""
    if canonical_key:
        mapping = REVIEWED_IMAGE_SOURCES.get(canonical_key)
        if mapping:
            return mapping
    if tcgplayer_set_id:
        return _BY_PROVIDER_ID.get(str(tcgplayer_set_id).strip())
    return None


def refusal_reason(canonical_key: str) -> Optional[str]:
    """Why a catalog was reviewed and deliberately left unmapped."""
    return REFUSED_CATALOGS.get(canonical_key)


def classify(canonical_key: str, tcgplayer_set_id: Optional[str] = None) -> str:
    mapping = resolve(canonical_key=canonical_key, tcgplayer_set_id=tcgplayer_set_id)
    return mapping.match_kind if mapping else NO_EQUIVALENT


def image_source_api_set_ids(
    canonical_key: Optional[str] = None, tcgplayer_set_id: Optional[str] = None
) -> Tuple[str, ...]:
    """API set ids images may be read from. Empty when the catalog is unmapped."""
    mapping = resolve(canonical_key=canonical_key, tcgplayer_set_id=tcgplayer_set_id)
    return mapping.api_set_ids if mapping else ()
