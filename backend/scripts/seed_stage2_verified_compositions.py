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
from typing import Any, Dict, List

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
]


def seed(*, commit: bool) -> Dict[str, Any]:
    from backend.db.repositories.sealed_product_compositions_repository import (
        upsert_composition,
    )

    results: List[Dict[str, Any]] = []
    for entry in VERIFIED_COMPOSITIONS:
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
            verified_at=VERIFIED_AT,
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
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(os.path.join(_PROJECT_ROOT, "backend", ".env"), override=False)

    print(json.dumps(seed(commit=args.commit), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
