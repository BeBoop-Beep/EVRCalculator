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

EVERY ROW HERE IS VERIFIED FROM A PRIMARY SOURCE
------------------------------------------------
Only compositions whose pack count AND exact guaranteed printings were confirmed
on Pokemon.com are recorded with ``status = 'verified'``. A product whose promo
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
# DELIBERATELY ABSENT: Paradox Rift, Temporal Forces and Mega Evolution. Their
# SKUs are split by SLEEVE ART ("[Iron Valiant]" / "[Roaring Moon]") while the
# source says the promo is "Scream Tail or Iron Bundle" - it explicitly treats
# sleeve and promo as independent choices. No primary source ties a printing to
# a SKU, and `card_components` names an EXACT variant, so those products stay
# unresolved in the coverage manifest rather than entering this table as a guess.
VERIFIED_AT_BATCH1 = "2026-08-16"

JOURNEY_TOGETHER_SET_ID = "142d3869-9d39-48b6-a810-751af2aac748"
DESTINED_RIVALS_SET_ID = "de291399-ead5-41dc-bc12-e7c587684f85"
BLACK_BOLT_SET_ID = "41a0ac1c-27ca-444b-8665-8ba35e583a3b"
WHITE_FLARE_SET_ID = "c38df164-ea0d-4e9e-bae6-4c3a517beb8f"
PHANTASMAL_FLAMES_SET_ID = "0f7e51e2-5a78-4500-9c9c-f690e934a069"

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


def _standard_etb(*, label, sealed_product_id, set_id, source, promo_name, variant_id):
    return {
        "label": label,
        "sealed_product_id": sealed_product_id,
        "source_type": "pokemon_com_product_page",
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
    *, label, sealed_product_id, set_id, source, promo_name, stamped_variant_id, variant_id
):
    return {
        "label": label,
        "sealed_product_id": sealed_product_id,
        "source_type": "pokemon_com_product_page",
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
