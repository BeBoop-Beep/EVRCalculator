"""Seed researched, source-backed Stage 2 sealed-product compositions.

WHY A REGISTRY IN CODE AND NOT A ONE-OFF SQL SCRIPT
---------------------------------------------------
A composition asserts what is physically inside a sealed box, and migration 066
made provenance NOT NULL precisely so that assertion is never anonymous. Keeping
the researched rows here - next to their citations, in a file that reviews like
code - means the claim and its evidence move together, and re-running the seeder
is the same operation as correcting it: writes are idempotent on
``(sealed_product_id, composition_version)`` and component sets are REPLACED, so
the database always equals this file.

It deliberately writes through ``sealed_product_compositions_repository`` rather
than raw SQL, so the seeder cannot bypass the component-replacement semantics the
resolver depends on.

EVERY ROW HERE HAS EXPLICIT, REVIEWABLE PROVENANCE
-------------------------------------------------
Most compositions are verified from Pokemon.com. A small number of exact
SKU-to-printing mappings use an identified commercial catalog, and the Dollar
General ETB uses the explicitly approved high-confidence secondary evidence tier;
their ``source_type`` records that distinction honestly. A product whose promo
exists physically but has no ``card_variants`` row in this database is NOT seeded
as a draft with a guessed variant - it is left absent, so the Stage 2 manifest
reports it as ``unresolved_promo_identity`` rather than scoring a substitute.

Usage::

    python -m backend.scripts.seed_stage2_verified_compositions            # dry run
    python -m backend.scripts.seed_stage2_verified_compositions --commit
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Set

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

#: Bumped only when the ASSERTED CONTENTS of a box change - never for a price
#: refresh or a re-run. Result rows record the version they scored.
COMPOSITION_VERSION = "stage2-verified-composition-v1"

# Set the random packs come from. Stage 2 is same-set only.
SV_BASE_SET_ID = "3c459327-59d0-41d5-b21e-aae36361cc77"

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
# Standard ETB: "9 Pokemon TCG: Scarlet & Violet booster packs" and
# "1 full-art foil promo card featuring Koraidon or Miraidon".
SOURCE_STANDARD_ETB = (
    "https://www.pokemon.com/us/pokemon-tcg/product-gallery/scarlet-violet-elite-trainer-box"
)
# Pokemon Center ETB: "11 Pokemon TCG: Scarlet & Violet booster packs", plus TWO
# promos - one "with a Pokemon Center logo" and one without.
SOURCE_POKEMON_CENTER_ETB = (
    "https://www.pokemon.com/us/pokemon-news/"
    "exclusive-pokemon-tcg-scarlet-and-violet-elite-trainer-boxes-at-the-pokemon-center"
)

VERIFIED_AT = "2026-08-15"

# ---------------------------------------------------------------------------
# Batch 1 (verified 2026-08-16)
# ---------------------------------------------------------------------------
# Four SV-era sets whose ETB promo is a SINGLE FIXED card on the pokemon.com
# product-gallery page. Each follows the shape SV base established: the standard
# ETB is 9 packs + one promo, and the Pokemon Center ETB is 11 packs ("two more
# than a usual Elite Trainer Box") + the SAME promo twice - once with a Pokemon
# Center logo and once without.
#
# Later resolved product-specific evidence for the split-art Paradox Rift,
# Temporal Forces, and Mega Evolution SKUs is recorded in the backlog block.
VERIFIED_AT_BATCH1 = "2026-08-16"

JOURNEY_TOGETHER_SET_ID = "142d3869-9d39-48b6-a810-751af2aac748"
DESTINED_RIVALS_SET_ID = "de291399-ead5-41dc-bc12-e7c587684f85"
BLACK_BOLT_SET_ID = "41a0ac1c-27ca-444b-8665-8ba35e583a3b"
WHITE_FLARE_SET_ID = "c38df164-ea0d-4e9e-bae6-4c3a517beb8f"
PHANTASMAL_FLAMES_SET_ID = "0f7e51e2-5a78-4500-9c9c-f690e934a069"
ASCENDED_HEROES_SET_ID = "75cd439d-aaa2-41cb-86f3-2fefa5b26e29"
PERFECT_ORDER_SET_ID = "5e99f658-39f0-4845-9228-db8db3965f32"
PALDEA_EVOLVED_SET_ID = "202518a0-5e86-4949-b1cd-c1c8ad95b616"
OBSIDIAN_FLAMES_SET_ID = "b4b34b61-ce48-4fc4-bd91-201a350b2600"
PALDEAN_FATES_SET_ID = "fd1538dd-36b9-4d02-98dc-fd65a5230d27"
SV151_SET_ID = "d001d563-988b-4f8e-904f-acb926748e22"
TWILIGHT_MASQUERADE_SET_ID = "cb68bfe9-53a6-4345-b0e3-f6cd6c33383b"
SHROUDED_FABLE_SET_ID = "3b753fb6-a465-4e68-8ad9-4e34e114d4b7"
STELLAR_CROWN_SET_ID = "4b15f040-4351-41ea-90e1-c07eb1b2f4d6"
SURGING_SPARKS_SET_ID = "f59f25a2-d3da-4100-a918-901271a99925"
PRISMATIC_EVOLUTIONS_SET_ID = "7a3dd188-4375-41af-94de-c5247fe0b1a6"

SOURCE_JOURNEY_TOGETHER_ETB = (
    "https://www.pokemon.com/us/pokemon-tcg/product-gallery/"
    "scarlet-violet-journey-together-elite-trainer-box"
)
SOURCE_JOURNEY_TOGETHER_PC_ETB = (
    "https://www.pokemon.com/us/pokemon-tcg/product-gallery/"
    "scarlet-violet-journey-together-pokemon-center-elite-trainer-box"
)
SOURCE_DESTINED_RIVALS_ETB = (
    "https://www.pokemon.com/us/pokemon-tcg/product-gallery/"
    "scarlet-violet-destined-rivals-elite-trainer-box"
)
SOURCE_DESTINED_RIVALS_PC_ETB = (
    "https://www.pokemon.com/us/pokemon-tcg/product-gallery/"
    "scarlet-violet-destined-rivals-pokemon-center-elite-trainer-box"
)
# Black Bolt and White Flare share one product-gallery page per family, because
# they released as a split expansion.
SOURCE_BLACK_BOLT_WHITE_FLARE_ETB = (
    "https://www.pokemon.com/us/pokemon-tcg/product-gallery/"
    "scarlet-violet-black-bolt-elite-trainer-box-scarlet-violet-white-flare-elite-trainer-box"
)
SOURCE_BLACK_BOLT_WHITE_FLARE_PC_ETB = (
    "https://www.pokemon.com/us/pokemon-tcg/product-gallery/"
    "scarlet-violet-black-bolt-pokemon-center-elite-trainer-box-"
    "scarlet-violet-white-flare-pokemon-center-elite-trainer-box"
)
SOURCE_PHANTASMAL_FLAMES_ETB = (
    "https://www.pokemon.com/us/pokemon-tcg/product-gallery/"
    "mega-evolution-phantasmal-flames-elite-trainer-box"
)
SOURCE_ASCENDED_HEROES_ETBS = (
    "https://www.pokemon.com/uk/pokemon-news/"
    "pokemon-tcg-mega-evolution-ascended-heroes-product-showcase"
)
SOURCE_PERFECT_ORDER_ETBS = (
    "https://www.pokemon.com/us/pokemon-news/"
    "check-out-every-pokemon-tcg-product-release-in-march-2026"
)
SOURCE_PHANTASMAL_FLAMES_PC_ETB = (
    "https://www.pokemon.com/us/pokemon-tcg/product-gallery/"
    "mega-evolution-phantasmal-flames-pokemon-center-elite-trainer-box"
)

def _product_page(slug: str) -> str:
    return f"https://www.pokemon.com/us/pokemon-tcg/product-gallery/{slug}"

# Exact printings, all in the SV Black Star Promo catalog and all NM-priced.
NS_ZORUA_189 = "06613c96-c91f-4701-b25d-8613c643a176"
NS_ZORUA_189_PC = "ac3ec399-043d-43fb-82be-601edbdd4d33"
TR_WOBBUFFET = "d2e198a2-4f96-4d92-9289-0d2ae60d3285"
TR_WOBBUFFET_PC = "f346066e-94a7-4a17-b38e-481852e40d2a"
THUNDURUS_209 = "12757765-c6b1-4f9c-a2c3-70f72ba7618e"
THUNDURUS_209_PC = "227fc031-f6ab-437e-9f01-c3144580127c"
TORNADUS_210 = "dcfea6e5-24ea-4206-9fc2-feeb57a7634f"
TORNADUS_210_PC = "c0a89300-34e5-4e75-8d00-0cad040b8679"
CHARCADET_022 = "52390f95-77b2-4a00-972f-a6b824c085f6"
NS_ZEKROM_031 = "2d869bb4-6ee1-4a46-9760-81bd30fbabc0"
NS_ZEKROM_031_PC = "e1f9109c-009d-417f-82dc-d4e0cd78cdbc"
TYRUNT_070 = "d50012b8-07cf-40b0-94ea-0cba23000451"
TYRUNT_070_PC = "53c9a84b-4bda-4400-b957-6622a42ba87f"
MEP_CHARCADET_022 = "bd6e5260-fee4-4a05-a858-5410b7afa0ab"
MEP_CHARCADET_022_PC = "2355b698-cc57-4ef9-8530-bcd134df69f9"
PIKACHU_027 = "55309cff-77d8-4517-aacd-c8098c21a99d"
PIKACHU_027_PC = "1f479b15-ab7a-431f-9e6e-cb5e82474bbb"
CHARMANDER_044 = "534a22bb-5c32-430d-8957-6182131ff610"
CHARMANDER_044_PC = "63f20f36-fb3e-4eaf-82e5-2dc74de6a8e8"
MIMIKYU_075 = "b43193da-d79c-4980-b379-70d6e3db2f63"
MIMIKYU_075_PC = "34b618e6-133d-4623-8ee9-d52d8eb200a8"
SNORLAX_051 = "9040b7b9-73e6-4380-bcd2-d89eba4b37a3"
SNORLAX_051_PC = "1d544f1c-0381-409d-9511-059a961b1289"
TEAL_MASK_OGERPON_123 = "7fd75829-af9f-4f2e-a5fe-be852e7119c0"
TEAL_MASK_OGERPON_123_PC = "d0e65ad1-c75d-46e1-89cd-3180b18def28"
PECHARUNT_129 = "1e4b7829-106c-4c03-abdc-ad24ce649ea8"
PECHARUNT_129_PC = "5aeb2c31-2f6a-4d95-a5e6-1dacf31a77f4"
NOCTOWL_141 = "e2b64556-2324-4f3f-a2da-d50d94a35e73"
NOCTOWL_141_PC = "2df72129-706e-4fe3-bb47-5b9d2162f1b6"
MAGNETON_159 = "f804efd8-b9c3-4b2a-b0d1-504ff3c47ade"
MAGNETON_159_PC = "6def01fe-b0fb-4667-a277-1067437e97e7"
EEVEE_173 = "4054c21f-ec33-4085-9807-75ab78a336e5"
EEVEE_173_PC = "eb4c4228-7ae2-4c0e-baab-e59775bae487"


def _standard_etb(*, label, sealed_product_id, set_id, source, promo_name, variant_id,
                  source_type="pokemon_com_product_page"):
    return {
        "label": label,
        "sealed_product_id": sealed_product_id,
        "source_type": source_type,
        "source_reference": source,
        "verified_at": VERIFIED_AT_BATCH1,
        "notes": f"9 packs + 1 full-art foil promo card featuring {promo_name}.",
        "pack_components": [{"set_id": set_id, "pack_count": 9}],
        "guaranteed_card_components": [
            {
                "card_variant_id": variant_id,
                "canonical_card_id": None,
                "quantity": 1,
                "component_role": "standard_etb_promo",
            }
        ],
    }


def _pokemon_center_etb(
    *, label, sealed_product_id, set_id, source, promo_name, stamped_variant_id, variant_id,
    source_type="pokemon_com_product_page"
):
    return {
        "label": label,
        "sealed_product_id": sealed_product_id,
        "source_type": source_type,
        "source_reference": source,
        "verified_at": VERIFIED_AT_BATCH1,
        "notes": (
            f"11 packs (two more than the standard ETB) + TWO full-art foil promos "
            f"featuring {promo_name}: one with a Pokemon Center logo and one without."
        ),
        "pack_components": [{"set_id": set_id, "pack_count": 11}],
        "guaranteed_card_components": [
            {
                "card_variant_id": stamped_variant_id,
                "canonical_card_id": None,
                "quantity": 1,
                "component_role": "pokemon_center_stamped_promo",
            },
            {
                "card_variant_id": variant_id,
                "canonical_card_id": None,
                "quantity": 1,
                "component_role": "pokemon_center_standard_promo",
            },
        ],
    }

# ---------------------------------------------------------------------------
# Exact guaranteed printings
# ---------------------------------------------------------------------------
# `canonical_card_id` is None for all of these: the SV Black Star Promo catalog
# has ZERO rows in pokemon_canonical_cards (no unique Pokemon TCG API set match),
# and the canonical model cannot express a Pokemon Center stamp at all. The
# card_variant_id is the authority - see migration 066's header note.
KORAIDON_014 = "635833b7-1004-4ee2-89db-0354f9b012a1"           # "Koraidon - 014"
KORAIDON_014_PC = "6559689f-9b9b-49df-a086-3102266b74be"        # "... (Pokemon Center Exclusive)"
MIRAIDON_013 = "7d68e753-5400-4f6d-a714-fe7a5a84ec68"           # "Miraidon - 013"
MIRAIDON_013_PC = "8a81e5cc-854c-4704-ad43-b531e2f921f5"        # "... (Pokemon Center Exclusive)"


VERIFIED_COMPOSITIONS: List[Dict[str, Any]] = [
    {
        "label": "Scarlet & Violet Elite Trainer Box [Koraidon]",
        "sealed_product_id": "2b49275d-a197-4e7c-9e8a-9bb6d79a0b50",
        "source_type": "pokemon_com_product_page",
        "source_reference": SOURCE_STANDARD_ETB,
        "notes": "9 packs + 1 full-art foil promo; Koraidon artwork variant.",
        "pack_components": [{"set_id": SV_BASE_SET_ID, "pack_count": 9}],
        "guaranteed_card_components": [
            {
                "card_variant_id": KORAIDON_014,
                "canonical_card_id": None,
                "quantity": 1,
                "component_role": "standard_etb_promo",
            }
        ],
    },
    {
        "label": "Scarlet & Violet Elite Trainer Box [Miraidon]",
        "sealed_product_id": "000aa2f2-bf00-485e-9c96-bb3a815b4ecd",
        "source_type": "pokemon_com_product_page",
        "source_reference": SOURCE_STANDARD_ETB,
        "notes": "9 packs + 1 full-art foil promo; Miraidon artwork variant.",
        "pack_components": [{"set_id": SV_BASE_SET_ID, "pack_count": 9}],
        "guaranteed_card_components": [
            {
                "card_variant_id": MIRAIDON_013,
                "canonical_card_id": None,
                "quantity": 1,
                "component_role": "standard_etb_promo",
            }
        ],
    },
    {
        "label": "Scarlet & Violet Pokemon Center Elite Trainer Box (Exclusive) [Koraidon]",
        "sealed_product_id": "8ad7a26b-d0ef-4060-998c-73afdf0c9d0e",
        "source_type": "pokemon_com_product_page",
        "source_reference": SOURCE_POKEMON_CENTER_ETB,
        "notes": (
            "11 packs (two more than the standard ETB) + TWO full-art foil promos: "
            "one Pokemon Center-logo printing and one ordinary printing."
        ),
        "pack_components": [{"set_id": SV_BASE_SET_ID, "pack_count": 11}],
        "guaranteed_card_components": [
            {
                "card_variant_id": KORAIDON_014_PC,
                "canonical_card_id": None,
                "quantity": 1,
                "component_role": "pokemon_center_stamped_promo",
            },
            {
                "card_variant_id": KORAIDON_014,
                "canonical_card_id": None,
                "quantity": 1,
                "component_role": "pokemon_center_standard_promo",
            },
        ],
    },
    {
        "label": "Scarlet & Violet Pokemon Center Elite Trainer Box (Exclusive) [Miraidon]",
        "sealed_product_id": "e827c1cd-9025-46d8-93f7-c14915bc52bf",
        "source_type": "pokemon_com_product_page",
        "source_reference": SOURCE_POKEMON_CENTER_ETB,
        "notes": (
            "11 packs (two more than the standard ETB) + TWO full-art foil promos: "
            "one Pokemon Center-logo printing and one ordinary printing."
        ),
        "pack_components": [{"set_id": SV_BASE_SET_ID, "pack_count": 11}],
        "guaranteed_card_components": [
            {
                "card_variant_id": MIRAIDON_013_PC,
                "canonical_card_id": None,
                "quantity": 1,
                "component_role": "pokemon_center_stamped_promo",
            },
            {
                "card_variant_id": MIRAIDON_013,
                "canonical_card_id": None,
                "quantity": 1,
                "component_role": "pokemon_center_standard_promo",
            },
        ],
    },
    # ---- Batch 1 -----------------------------------------------------------
    _standard_etb(
        label="Journey Together Elite Trainer Box",
        sealed_product_id="751c3d34-5555-42bc-a98b-694ad481dd46",
        set_id=JOURNEY_TOGETHER_SET_ID,
        source=SOURCE_JOURNEY_TOGETHER_ETB,
        promo_name="N's Zorua",
        variant_id=NS_ZORUA_189,
    ),
    _pokemon_center_etb(
        label="Journey Together Pokemon Center Elite Trainer Box (Exclusive)",
        sealed_product_id="5ad414d2-9297-4995-be00-dd4f468cbd0d",
        set_id=JOURNEY_TOGETHER_SET_ID,
        source=SOURCE_JOURNEY_TOGETHER_PC_ETB,
        promo_name="N's Zorua",
        stamped_variant_id=NS_ZORUA_189_PC,
        variant_id=NS_ZORUA_189,
    ),
    _standard_etb(
        label="Destined Rivals Elite Trainer Box",
        sealed_product_id="1de25f6a-cbc8-49e4-8092-85e549c89604",
        set_id=DESTINED_RIVALS_SET_ID,
        source=SOURCE_DESTINED_RIVALS_ETB,
        promo_name="Team Rocket's Wobbuffet",
        variant_id=TR_WOBBUFFET,
    ),
    _pokemon_center_etb(
        label="Destined Rivals Pokemon Center Elite Trainer Box (Exclusive)",
        sealed_product_id="3dc67a73-3cd3-435a-98cc-282729eff65b",
        set_id=DESTINED_RIVALS_SET_ID,
        source=SOURCE_DESTINED_RIVALS_PC_ETB,
        promo_name="Team Rocket's Wobbuffet",
        stamped_variant_id=TR_WOBBUFFET_PC,
        variant_id=TR_WOBBUFFET,
    ),
    _standard_etb(
        label="Black Bolt Elite Trainer Box",
        sealed_product_id="ba26fc56-5ea7-4a92-97bf-816881d7e892",
        set_id=BLACK_BOLT_SET_ID,
        source=SOURCE_BLACK_BOLT_WHITE_FLARE_ETB,
        promo_name="Thundurus",
        variant_id=THUNDURUS_209,
    ),
    _pokemon_center_etb(
        label="Black Bolt Pokemon Center Elite Trainer Box (Exclusive)",
        sealed_product_id="fe2349b8-9f72-487d-b831-b58e83a05d88",
        set_id=BLACK_BOLT_SET_ID,
        source=SOURCE_BLACK_BOLT_WHITE_FLARE_PC_ETB,
        promo_name="Thundurus",
        stamped_variant_id=THUNDURUS_209_PC,
        variant_id=THUNDURUS_209,
    ),
    _standard_etb(
        label="White Flare Elite Trainer Box",
        sealed_product_id="18ded802-ec1d-4247-b29a-2e07e41f9bf2",
        set_id=WHITE_FLARE_SET_ID,
        source=SOURCE_BLACK_BOLT_WHITE_FLARE_ETB,
        promo_name="Tornadus",
        variant_id=TORNADUS_210,
    ),
    _pokemon_center_etb(
        label="White Flare Pokemon Center Elite Trainer Box (Exclusive)",
        sealed_product_id="55dc35f0-a0ab-49ed-83b9-0a47b863a779",
        set_id=WHITE_FLARE_SET_ID,
        source=SOURCE_BLACK_BOLT_WHITE_FLARE_PC_ETB,
        promo_name="Tornadus",
        stamped_variant_id=TORNADUS_210_PC,
        variant_id=TORNADUS_210,
    ),
    _standard_etb(
        label="Phantasmal Flames Elite Trainer Box",
        sealed_product_id="0c96f395-8263-458b-bc49-ed3dbbf5a3a6",
        set_id=PHANTASMAL_FLAMES_SET_ID,
        source=SOURCE_PHANTASMAL_FLAMES_ETB,
        promo_name="Charcadet (022)",
        variant_id=CHARCADET_022,
    ),
    _standard_etb(
        label="Ascended Heroes Elite Trainer Box",
        sealed_product_id="69bfec2f-3b89-4c34-b6af-3f2e3c0d4c4b",
        set_id=ASCENDED_HEROES_SET_ID,
        source=SOURCE_ASCENDED_HEROES_ETBS,
        promo_name="N's Zekrom (031)",
        variant_id=NS_ZEKROM_031,
    ),
    _pokemon_center_etb(
        label="Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive)",
        sealed_product_id="8d2df1b7-21f0-4671-8dd9-5da9bbb8e515",
        set_id=ASCENDED_HEROES_SET_ID,
        source=SOURCE_ASCENDED_HEROES_ETBS,
        promo_name="N's Zekrom (031)",
        stamped_variant_id=NS_ZEKROM_031_PC,
        variant_id=NS_ZEKROM_031,
    ),
    _standard_etb(
        label="Perfect Order Elite Trainer Box",
        sealed_product_id="f0e6a6b6-5fe7-427b-b95f-544a7cd1477c",
        set_id=PERFECT_ORDER_SET_ID,
        source=SOURCE_PERFECT_ORDER_ETBS,
        promo_name="Tyrunt (070)",
        variant_id=TYRUNT_070,
    ),
    _pokemon_center_etb(
        label="Perfect Order Pokemon Center Elite Trainer Box",
        sealed_product_id="bf6b69d8-98b3-4baa-a9a5-74d657ec6f8c",
        set_id=PERFECT_ORDER_SET_ID,
        source=SOURCE_PERFECT_ORDER_ETBS,
        promo_name="Tyrunt (070)",
        stamped_variant_id=TYRUNT_070_PC,
        variant_id=TYRUNT_070,
    ),
    _pokemon_center_etb(
        label="Phantasmal Flames Pokemon Center Elite Trainer Box (Exclusive)",
        sealed_product_id="c9efb943-605a-4ed6-8ed8-8eb5d0ef2c41",
        set_id=PHANTASMAL_FLAMES_SET_ID,
        source=SOURCE_PHANTASMAL_FLAMES_PC_ETB,
        promo_name="Charcadet (022)",
        stamped_variant_id=MEP_CHARCADET_022_PC,
        variant_id=MEP_CHARCADET_022,
    ),
    # ---- Non-Mega Stage 2 research (2026-08-16) --------------------------
    _standard_etb(label="Paldea Evolved Elite Trainer Box", sealed_product_id="4e9d90e0-4628-4748-83b3-51da7db11344", set_id=PALDEA_EVOLVED_SET_ID, source=_product_page("scarlet-violet-paldea-evolved-elite-trainer-box"), promo_name="Pikachu (027)", variant_id=PIKACHU_027),
    _pokemon_center_etb(label="Paldea Evolved Pokemon Center Elite Trainer Box (Exclusive)", sealed_product_id="cea689d1-46d0-48b7-850a-ff6cf44fa71e", set_id=PALDEA_EVOLVED_SET_ID, source=_product_page("scarlet-violet-paldea-evolved-pokemon-center-elite-trainer-box"), promo_name="Pikachu (027)", stamped_variant_id=PIKACHU_027_PC, variant_id=PIKACHU_027),
    _standard_etb(label="Obsidian Flames Elite Trainer Box", sealed_product_id="b1e99164-f8bd-4188-8c8f-e225586efb5f", set_id=OBSIDIAN_FLAMES_SET_ID, source=_product_page("scarlet-violet-obsidian-flames-elite-trainer-box"), promo_name="Charmander (044)", variant_id=CHARMANDER_044),
    _pokemon_center_etb(label="Obsidian Flames Pokemon Center Elite Trainer Box (Exclusive)", sealed_product_id="3b520d86-ecc5-4bd9-8f56-5050e1c4a4d9", set_id=OBSIDIAN_FLAMES_SET_ID, source=_product_page("scarlet-violet-obsidian-flames-pokemon-center-elite-trainer-box"), promo_name="Charmander (044)", stamped_variant_id=CHARMANDER_044_PC, variant_id=CHARMANDER_044),
    _standard_etb(label="Paldean Fates Elite Trainer Box", sealed_product_id="808537c4-4136-4d23-a3b2-f5984cf474e2", set_id=PALDEAN_FATES_SET_ID, source=_product_page("scarlet-violet-paldean-fates-elite-trainer-box"), promo_name="Mimikyu (075)", variant_id=MIMIKYU_075),
    _pokemon_center_etb(label="Paldean Fates Pokemon Center Elite Trainer Box (Exclusive)", sealed_product_id="86d73a43-aacf-4793-a0db-5b043b35a2f6", set_id=PALDEAN_FATES_SET_ID, source=_product_page("scarlet-violet-paldean-fates-pokemon-center-elite-trainer-box"), promo_name="Mimikyu (075)", stamped_variant_id=MIMIKYU_075_PC, variant_id=MIMIKYU_075),
    _standard_etb(label="151 Elite Trainer Box", sealed_product_id="80b07fe1-5561-414a-a60b-b03689f481a9", set_id=SV151_SET_ID, source=_product_page("scarlet-violet-151-elite-trainer-box"), promo_name="Snorlax (051)", variant_id=SNORLAX_051),
    _pokemon_center_etb(label="151 Pokemon Center Elite Trainer Box (Exclusive)", sealed_product_id="dbfd9f2d-5509-45b2-a08f-ba5e09ad2ff4", set_id=SV151_SET_ID, source=_product_page("scarlet-violet-151-pokemon-center-elite-trainer-box"), promo_name="Snorlax (051)", stamped_variant_id=SNORLAX_051_PC, variant_id=SNORLAX_051),
    _standard_etb(label="Twilight Masquerade Elite Trainer Box", sealed_product_id="c021a1d3-54b2-46f6-bf82-1454fff78aa6", set_id=TWILIGHT_MASQUERADE_SET_ID, source=_product_page("scarlet-violet-twilight-masquerade-elite-trainer-box"), promo_name="Teal Mask Ogerpon (123)", variant_id=TEAL_MASK_OGERPON_123),
    _pokemon_center_etb(label="Twilight Masquerade Pokemon Center Elite Trainer Box (Exclusive)", sealed_product_id="0a8fa379-222a-41d2-8c13-afee4e663fc4", set_id=TWILIGHT_MASQUERADE_SET_ID, source=_product_page("scarlet-violet-twilight-masquerade-pokemon-center-elite-trainer-box"), promo_name="Teal Mask Ogerpon (123)", stamped_variant_id=TEAL_MASK_OGERPON_123_PC, variant_id=TEAL_MASK_OGERPON_123),
    _standard_etb(label="Shrouded Fable Elite Trainer Box", sealed_product_id="fb5ad13c-4075-4c3b-b20d-9ad382961436", set_id=SHROUDED_FABLE_SET_ID, source=_product_page("scarlet-violet-shrouded-fable-elite-trainer-box"), promo_name="Pecharunt (129)", variant_id=PECHARUNT_129),
    _pokemon_center_etb(label="Shrouded Fable Pokemon Center Elite Trainer Box (Exclusive)", sealed_product_id="31b771c4-67ca-46c7-840c-e39ed91e0189", set_id=SHROUDED_FABLE_SET_ID, source=_product_page("scarlet-violet-shrouded-fable-pokemon-center-elite-trainer-box"), promo_name="Pecharunt (129)", stamped_variant_id=PECHARUNT_129_PC, variant_id=PECHARUNT_129),
    _standard_etb(label="Stellar Crown Elite Trainer Box", sealed_product_id="928eeef5-8a7e-4c1f-a634-ae332c8c0219", set_id=STELLAR_CROWN_SET_ID, source=_product_page("scarlet-violet-stellar-crown-elite-trainer-box"), promo_name="Noctowl (141)", variant_id=NOCTOWL_141),
    _pokemon_center_etb(label="Stellar Crown Pokemon Center Elite Trainer Box (Exclusive)", sealed_product_id="a3610e17-f0d0-4b4f-88a0-fb6374b0d458", set_id=STELLAR_CROWN_SET_ID, source=_product_page("scarlet-violet-stellar-crown-pokemon-center-elite-trainer-box"), promo_name="Noctowl (141)", stamped_variant_id=NOCTOWL_141_PC, variant_id=NOCTOWL_141),
    _standard_etb(label="Surging Sparks Elite Trainer Box", sealed_product_id="f8110028-665d-42d1-ab9d-7e17b784d638", set_id=SURGING_SPARKS_SET_ID, source=_product_page("scarlet-violet-surging-sparks-elite-trainer-box"), promo_name="Magneton (159)", variant_id=MAGNETON_159),
    _pokemon_center_etb(label="Surging Sparks Pokemon Center Elite Trainer Box (Exclusive)", sealed_product_id="55d50d9e-d68b-4f3b-b552-da2c065fad3f", set_id=SURGING_SPARKS_SET_ID, source=_product_page("scarlet-violet-surging-sparks-pokemon-center-elite-trainer-box"), promo_name="Magneton (159)", stamped_variant_id=MAGNETON_159_PC, variant_id=MAGNETON_159),
    _standard_etb(label="Prismatic Evolutions Elite Trainer Box", sealed_product_id="41b15cf2-512b-4b28-9660-83170538fc7a", set_id=PRISMATIC_EVOLUTIONS_SET_ID, source=_product_page("scarlet-violet-prismatic-evolutions-elite-trainer-box"), promo_name="Eevee (173)", variant_id=EEVEE_173),
    _pokemon_center_etb(label="Prismatic Evolutions Pokemon Center Elite Trainer Box (Exclusive)", sealed_product_id="f0b0297b-0f85-4abf-8fc7-2227c18488dd", set_id=PRISMATIC_EVOLUTIONS_SET_ID, source=_product_page("scarlet-violet-prismatic-evolutions-pokemon-center-elite-trainer-box"), promo_name="Eevee (173)", stamped_variant_id=EEVEE_173_PC, variant_id=EEVEE_173),
    # ---- Resolved deterministic backlog (2026-08-16) ---------------------
    _standard_etb(label="Paradox Rift Elite Trainer Box [Iron Valiant]", sealed_product_id="53577dca-8d1c-43b8-aa29-7d1db999c8a2", set_id="5d3d5c23-7098-4393-ad63-6ad9372aee30", source="https://www.tcgplayer.com/search/pokemon/sv-paradox-rift/product", promo_name="Iron Bundle (066)", variant_id="9c7f6112-e61c-4722-9718-0d696e3c4652", source_type="product_catalog"),
    _pokemon_center_etb(label="Paradox Rift Pokemon Center Elite Trainer Box (Exclusive) [Iron Valiant]", sealed_product_id="d912f454-ebfc-439d-9c53-44b7eadfba60", set_id="5d3d5c23-7098-4393-ad63-6ad9372aee30", source="https://www.tcgplayer.com/search/pokemon/sv-paradox-rift/product", promo_name="Iron Bundle (066)", stamped_variant_id="34ee05d1-34a9-45b5-a089-f0a9f4bdbc39", variant_id="9c7f6112-e61c-4722-9718-0d696e3c4652", source_type="product_catalog"),
    _standard_etb(label="Paradox Rift Elite Trainer Box [Roaring Moon]", sealed_product_id="302a4fe7-eda9-4d83-9157-5a4161714a6f", set_id="5d3d5c23-7098-4393-ad63-6ad9372aee30", source="https://www.tcgplayer.com/search/pokemon/sv-paradox-rift/product", promo_name="Scream Tail (065)", variant_id="36f6a49b-abf6-495d-813e-6b107972f39d", source_type="product_catalog"),
    _pokemon_center_etb(label="Paradox Rift Pokemon Center Elite Trainer Box (Exclusive) [Roaring Moon]", sealed_product_id="c67bc92a-e4ab-4bd6-8f8c-90b59024b859", set_id="5d3d5c23-7098-4393-ad63-6ad9372aee30", source="https://www.tcgplayer.com/search/pokemon/sv-paradox-rift/product", promo_name="Scream Tail (065)", stamped_variant_id="a97045f4-d421-4de1-88c6-d1300165fdab", variant_id="36f6a49b-abf6-495d-813e-6b107972f39d", source_type="product_catalog"),
    _standard_etb(label="Temporal Forces Elite Trainer Box [Iron Leaves ex]", sealed_product_id="44927dc3-68cd-4a24-abb7-019dc2acb22b", set_id="91442900-3949-4ba4-8398-9e3dc2db1fa6", source="https://www.tcgplayer.com/search/pokemon/sv-temporal-forces/product", promo_name="Iron Thorns (098)", variant_id="663a6f75-a5be-4070-b2c4-e4ff471b0c45", source_type="product_catalog"),
    _pokemon_center_etb(label="Temporal Forces Pokemon Center Elite Trainer Box (Exclusive) [Iron Leaves]", sealed_product_id="a6865906-21e1-439d-9cfe-e0deae8b81cf", set_id="91442900-3949-4ba4-8398-9e3dc2db1fa6", source="https://www.tcgplayer.com/search/pokemon/sv-temporal-forces/product", promo_name="Iron Thorns (098)", stamped_variant_id="c3e0b609-f2a2-46de-9dc3-c934524dd535", variant_id="663a6f75-a5be-4070-b2c4-e4ff471b0c45", source_type="product_catalog"),
    _standard_etb(label="Temporal Forces Elite Trainer Box [Walking Wake]", sealed_product_id="b02156c5-f2e8-4d01-8b6b-f763bdaf9b1a", set_id="91442900-3949-4ba4-8398-9e3dc2db1fa6", source="https://www.tcgplayer.com/search/pokemon/sv-temporal-forces/product", promo_name="Flutter Mane (097)", variant_id="d6d1c994-f488-4776-86a9-fa6c6c5d1ca5", source_type="product_catalog"),
    _pokemon_center_etb(label="Temporal Forces Pokemon Center Elite Trainer Box (Exclusive) [Walking Wake]", sealed_product_id="8a1b06aa-8312-42e2-a2c2-f576f42a5d1c", set_id="91442900-3949-4ba4-8398-9e3dc2db1fa6", source="https://www.tcgplayer.com/search/pokemon/sv-temporal-forces/product", promo_name="Flutter Mane (097)", stamped_variant_id="db11ca4e-5045-4fb9-a274-67c0ca52ca4f", variant_id="d6d1c994-f488-4776-86a9-fa6c6c5d1ca5", source_type="product_catalog"),
    _standard_etb(label="Mega Evolution Elite Trainer Box [Mega Gardevoir]", sealed_product_id="b1954a62-1157-4e54-9e1c-f0be478e2459", set_id="b3c96740-a4a9-4c3d-a8f6-81ed4584549d", source="https://www.tcgplayer.com/categories/trading-and-collectible-card-games/pokemon/me01-mega-evolution", promo_name="Alakazam (009)", variant_id="afa13738-6c09-4c0b-b18e-8768a5e6bcb0", source_type="product_catalog"),
    _pokemon_center_etb(label="Mega Evolution Pokemon Center Elite Trainer Box (Exclusive) [Mega Gardevoir]", sealed_product_id="d05d77e9-c05b-44af-9557-ce08abecc10e", set_id="b3c96740-a4a9-4c3d-a8f6-81ed4584549d", source="https://www.tcgplayer.com/categories/trading-and-collectible-card-games/pokemon/me01-mega-evolution", promo_name="Alakazam (009)", stamped_variant_id="8d7293b4-fdc4-46eb-bc25-5b4bb11cf383", variant_id="afa13738-6c09-4c0b-b18e-8768a5e6bcb0", source_type="product_catalog"),
    _standard_etb(label="Mega Evolution Elite Trainer Box [Mega Lucario]", sealed_product_id="b673944a-b456-4ece-9131-8b96f06da6e1", set_id="b3c96740-a4a9-4c3d-a8f6-81ed4584549d", source="https://www.tcgplayer.com/categories/trading-and-collectible-card-games/pokemon/me01-mega-evolution", promo_name="Riolu (010)", variant_id="ddb4f530-84e7-4534-9375-38177915433c", source_type="product_catalog"),
    _pokemon_center_etb(label="Mega Evolution Pokemon Center Elite Trainer Box (Exclusive) [Mega Lucario]", sealed_product_id="e0087cc5-963c-429d-a370-61384cc107f8", set_id="b3c96740-a4a9-4c3d-a8f6-81ed4584549d", source="https://www.tcgplayer.com/categories/trading-and-collectible-card-games/pokemon/me01-mega-evolution", promo_name="Riolu (010)", stamped_variant_id="4f76a1fb-2b8b-4b6b-bdb0-25bf6351e1ea", variant_id="ddb4f530-84e7-4534-9375-38177915433c", source_type="product_catalog"),
    _standard_etb(label="Chaos Rising Elite Trainer Box", sealed_product_id="682e91e8-020c-4293-bafe-eb19c62131ce", set_id="5bdbfae1-3f2e-44e7-b8c9-1035ad45b896", source="https://www.pokemon.com/us/pokemon-news/pokemon-tcg-mega-evolution-chaos-rising-product-showcase", promo_name="Fennekin (080)", variant_id="ce5e3c74-e806-4994-89db-dbbc7f67ce34"),
    _pokemon_center_etb(label="Chaos Rising Pokemon Center Elite Trainer Box", sealed_product_id="a98ce200-a891-4076-8c10-5130df7e5ad6", set_id="5bdbfae1-3f2e-44e7-b8c9-1035ad45b896", source="https://www.pokemon.com/us/pokemon-news/pokemon-tcg-mega-evolution-chaos-rising-product-showcase", promo_name="Fennekin (080)", stamped_variant_id="65d12343-5a4b-41b8-9aa5-d47af461d57d", variant_id="ce5e3c74-e806-4994-89db-dbbc7f67ce34"),
    _standard_etb(label="Pitch Black Elite Trainer Box", sealed_product_id="fe179039-b1d0-435d-a10c-c84db9d624b5", set_id="472f851c-2e41-4c80-b6fc-8478d1d92730", source=_product_page("mega-evolution-pitch-black-pokemon-center-elite-trainer-box"), promo_name="Zarude (088)", variant_id="b52415ef-c730-4d83-b108-4817e76f86d6"),
    _pokemon_center_etb(label="Pitch Black Pokemon Center Elite Trainer Box (Exclusive)", sealed_product_id="1513e48c-7ba2-414e-af27-762868c8239b", set_id="472f851c-2e41-4c80-b6fc-8478d1d92730", source=_product_page("mega-evolution-pitch-black-pokemon-center-elite-trainer-box"), promo_name="Zarude (088)", stamped_variant_id="7ffaf03b-8bec-4582-b03f-52cddebced23", variant_id="b52415ef-c730-4d83-b108-4817e76f86d6"),
    _standard_etb(label="Prismatic Evolutions Elite Trainer Box (Dollar General Exclusive)", sealed_product_id="342e0e74-6469-4546-8411-70a282be1b35", set_id=PRISMATIC_EVOLUTIONS_SET_ID, source="https://tcglookup.com/card/670608-prismatic-evolutions-elite-trainer-box-case-dollar-general-exclusive", promo_name="Eevee (173)", variant_id=EEVEE_173, source_type="archival_reference"),
    {"label": "Journey Together Enhanced Booster Box", "sealed_product_id": "aef45d06-1046-4d70-8941-de38a05f6ae2", "source_type": "product_catalog", "source_reference": "https://www.tcgplayer.com/product/623594", "verified_at": VERIFIED_AT_BATCH1, "notes": "36 Journey Together packs + exact Journey Together-stamped N's Reshiram 167/159 box-topper.", "pack_components": [{"set_id": JOURNEY_TOGETHER_SET_ID, "pack_count": 36}], "guaranteed_card_components": [{"card_variant_id": "e65517e4-1fef-4062-9959-51c96e360863", "canonical_card_id": None, "quantity": 1, "component_role": "enhanced_booster_box_stamped_topper"}]},
    {"label": "Mega Evolution Enhanced Booster Box", "sealed_product_id": "952bcc61-45c0-4717-8898-023f15d7ee30", "source_type": "product_catalog", "source_reference": "https://www.tcgplayer.com/product/654703", "verified_at": VERIFIED_AT_BATCH1, "notes": "36 Mega Evolution packs + exact Mega Evolution-stamped Bulbasaur 133/132 box-topper.", "pack_components": [{"set_id": "b3c96740-a4a9-4c3d-a8f6-81ed4584549d", "pack_count": 36}], "guaranteed_card_components": [{"card_variant_id": "514a999d-1ed3-44a9-a33c-b29ae7af8c96", "canonical_card_id": None, "quantity": 1, "component_role": "enhanced_booster_box_stamped_topper"}]},
]


def seed(*, commit: bool, sealed_product_ids: Optional[Set[str]] = None) -> Dict[str, Any]:
    from backend.db.repositories.sealed_product_compositions_repository import (
        upsert_composition,
    )

    results: List[Dict[str, Any]] = []
    for entry in VERIFIED_COMPOSITIONS:
        if sealed_product_ids and entry["sealed_product_id"] not in sealed_product_ids:
            continue
        row = {
            "label": entry["label"],
            "sealed_product_id": entry["sealed_product_id"],
            "composition_version": COMPOSITION_VERSION,
            "pack_count": sum(p["pack_count"] for p in entry["pack_components"]),
            "guaranteed_components": len(entry["guaranteed_card_components"]),
            "source_reference": entry["source_reference"],
        }
        if not commit:
            row["action"] = "would_upsert"
            results.append(row)
            continue

        written = upsert_composition(
            sealed_product_id=entry["sealed_product_id"],
            composition_version=COMPOSITION_VERSION,
            status="verified",
            source_type=entry["source_type"],
            source_reference=entry["source_reference"],
            verified_at=entry.get("verified_at", VERIFIED_AT),
            pack_components=entry["pack_components"],
            guaranteed_card_components=entry["guaranteed_card_components"],
            notes=entry["notes"],
        )
        row["action"] = "upserted"
        row["composition_id"] = written["composition_id"]
        results.append(row)

    return {
        "mode": "commit" if commit else "dry_run",
        "compositionVersion": COMPOSITION_VERSION,
        "compositions": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Write to the database. Omit to print what would be written.",
    )
    parser.add_argument(
        "--sealed-product-id",
        action="append",
        dest="sealed_product_ids",
        help="Limit the idempotent upsert to one or more exact sealed product IDs.",
    )
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(os.path.join(_PROJECT_ROOT, "backend", ".env"), override=False)

    print(
        json.dumps(
            seed(
                commit=args.commit,
                sealed_product_ids=set(args.sealed_product_ids or []) or None,
            ),
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
