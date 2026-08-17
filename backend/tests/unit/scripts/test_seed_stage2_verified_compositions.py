"""Contract tests for the Stage 2 verified-composition registry.

The registry is data, but it is data that asserts what is physically inside a
sealed box, so it is held to structural rules rather than reviewed by eye:
provenance is never blank, a SKU is never claimed twice, a Pokemon Center ETB
always carries exactly one stamped and one ordinary printing, and - the rule
that keeps the table honest - a SKU whose exact promo is NOT determined by a
primary source is absent rather than guessed.
"""

import pytest

from backend.scripts.seed_stage2_verified_compositions import (
    COMPOSITION_VERSION,
    VERIFIED_COMPOSITIONS,
)

BY_SKU = {entry["sealed_product_id"]: entry for entry in VERIFIED_COMPOSITIONS}

# Batch 1 (verified on pokemon.com product-gallery pages, 2026-08-16).
JOURNEY_TOGETHER_SET = "142d3869-9d39-48b6-a810-751af2aac748"
DESTINED_RIVALS_SET = "de291399-ead5-41dc-bc12-e7c587684f85"
BLACK_BOLT_SET = "41a0ac1c-27ca-444b-8665-8ba35e583a3b"
WHITE_FLARE_SET = "c38df164-ea0d-4e9e-bae6-4c3a517beb8f"

STANDARD_ETBS = {
    "751c3d34-5555-42bc-a98b-694ad481dd46": (JOURNEY_TOGETHER_SET, "06613c96-c91f-4701-b25d-8613c643a176"),
    "1de25f6a-cbc8-49e4-8092-85e549c89604": (DESTINED_RIVALS_SET, "d2e198a2-4f96-4d92-9289-0d2ae60d3285"),
    "ba26fc56-5ea7-4a92-97bf-816881d7e892": (BLACK_BOLT_SET, "12757765-c6b1-4f9c-a2c3-70f72ba7618e"),
    "18ded802-ec1d-4247-b29a-2e07e41f9bf2": (WHITE_FLARE_SET, "dcfea6e5-24ea-4206-9fc2-feeb57a7634f"),
}

# (set_id, stamped_variant_id, ordinary_variant_id)
POKEMON_CENTER_ETBS = {
    "5ad414d2-9297-4995-be00-dd4f468cbd0d": (
        JOURNEY_TOGETHER_SET,
        "ac3ec399-043d-43fb-82be-601edbdd4d33",
        "06613c96-c91f-4701-b25d-8613c643a176",
    ),
    "3dc67a73-3cd3-435a-98cc-282729eff65b": (
        DESTINED_RIVALS_SET,
        "f346066e-94a7-4a17-b38e-481852e40d2a",
        "d2e198a2-4f96-4d92-9289-0d2ae60d3285",
    ),
    "fe2349b8-9f72-487d-b831-b58e83a05d88": (
        BLACK_BOLT_SET,
        "227fc031-f6ab-437e-9f01-c3144580127c",
        "12757765-c6b1-4f9c-a2c3-70f72ba7618e",
    ),
    "55dc35f0-a0ab-49ed-83b9-0a47b863a779": (
        WHITE_FLARE_SET,
        "c0a89300-34e5-4e75-8d00-0cad040b8679",
        "dcfea6e5-24ea-4206-9fc2-feeb57a7634f",
    ),
}

RESOLVED_ARTWORK_PROMOS = {
    "53577dca-8d1c-43b8-aa29-7d1db999c8a2": "9c7f6112-e61c-4722-9718-0d696e3c4652",
    "302a4fe7-eda9-4d83-9157-5a4161714a6f": "36f6a49b-abf6-495d-813e-6b107972f39d",
    "44927dc3-68cd-4a24-abb7-019dc2acb22b": "663a6f75-a5be-4070-b2c4-e4ff471b0c45",
    "b02156c5-f2e8-4d01-8b6b-f763bdaf9b1a": "d6d1c994-f488-4776-86a9-fa6c6c5d1ca5",
    "b1954a62-1157-4e54-9e1c-f0be478e2459": "afa13738-6c09-4c0b-b18e-8768a5e6bcb0",
    "b673944a-b456-4ece-9131-8b96f06da6e1": "ddb4f530-84e7-4534-9375-38177915433c",
}


@pytest.mark.parametrize("sku_id", sorted(STANDARD_ETBS))
def test_standard_etb_is_nine_packs_and_one_promo(sku_id):
    set_id, variant_id = STANDARD_ETBS[sku_id]
    entry = BY_SKU[sku_id]

    assert entry["pack_components"] == [{"set_id": set_id, "pack_count": 9}]

    components = entry["guaranteed_card_components"]
    assert len(components) == 1
    assert components[0]["card_variant_id"] == variant_id
    assert components[0]["quantity"] == 1
    assert components[0]["component_role"] == "standard_etb_promo"


@pytest.mark.parametrize("sku_id", sorted(POKEMON_CENTER_ETBS))
def test_pokemon_center_etb_is_eleven_packs_and_both_printings(sku_id):
    set_id, stamped_id, ordinary_id = POKEMON_CENTER_ETBS[sku_id]
    entry = BY_SKU[sku_id]

    assert entry["pack_components"] == [{"set_id": set_id, "pack_count": 11}]

    by_role = {c["component_role"]: c for c in entry["guaranteed_card_components"]}
    assert set(by_role) == {"pokemon_center_stamped_promo", "pokemon_center_standard_promo"}
    assert by_role["pokemon_center_stamped_promo"]["card_variant_id"] == stamped_id
    assert by_role["pokemon_center_standard_promo"]["card_variant_id"] == ordinary_id
    assert all(c["quantity"] == 1 for c in by_role.values())


def test_every_composition_carries_real_provenance():
    for entry in VERIFIED_COMPOSITIONS:
        assert entry["source_type"] in {
            "pokemon_com_product_page",
            "pokemon_center_product_page",
            "pokemon_support",
            "product_catalog",
            "archival_reference",
        }
        assert entry["source_reference"].startswith("https://")
        assert entry["notes"].strip()
        assert entry["label"].strip()


def test_no_sku_is_claimed_twice():
    ids = [entry["sealed_product_id"] for entry in VERIFIED_COMPOSITIONS]
    assert len(ids) == len(set(ids))


def test_no_composition_lists_the_same_printing_twice():
    """Mirrors the DB unique constraint: two copies use quantity, not two rows."""
    for entry in VERIFIED_COMPOSITIONS:
        variant_ids = [c["card_variant_id"] for c in entry["guaranteed_card_components"]]
        assert len(variant_ids) == len(set(variant_ids)), entry["label"]


def test_pack_components_are_positive_and_single_set():
    for entry in VERIFIED_COMPOSITIONS:
        assert len(entry["pack_components"]) == 1, "Stage 2 is same-set only"
        assert entry["pack_components"][0]["pack_count"] > 0


def test_canonical_card_id_is_never_invented_for_promo_components():
    """The SV promo catalog has zero pokemon_canonical_cards rows."""
    for entry in VERIFIED_COMPOSITIONS:
        for component in entry["guaranteed_card_components"]:
            assert component["canonical_card_id"] is None


@pytest.mark.parametrize("sku_id,variant_id", RESOLVED_ARTWORK_PROMOS.items())
def test_resolved_artwork_sku_uses_exact_ordinary_promo(sku_id, variant_id):
    assert BY_SKU[sku_id]["guaranteed_card_components"][0]["card_variant_id"] == variant_id


def test_enhanced_booster_boxes_use_stamped_not_ordinary_variants():
    expected = {
        "aef45d06-1046-4d70-8941-de38a05f6ae2": ("e65517e4-1fef-4062-9959-51c96e360863", "e4d37898-c561-4b7b-85e2-d88e1caf71e1"),
        "952bcc61-45c0-4717-8898-023f15d7ee30": ("514a999d-1ed3-44a9-a33c-b29ae7af8c96", "ba7e74fb-58d2-4801-bed6-8e89d8ab812d"),
    }
    for sku_id, (stamped, ordinary) in expected.items():
        entry = BY_SKU[sku_id]
        assert entry["pack_components"][0]["pack_count"] == 36
        assert entry["guaranteed_card_components"][0]["card_variant_id"] == stamped
        assert stamped != ordinary


def test_each_composition_records_the_date_it_was_actually_verified():
    """verified_at is per-row: batch 1 was researched a day after the SV base rows."""
    for sku_id in list(STANDARD_ETBS) + list(POKEMON_CENTER_ETBS):
        assert BY_SKU[sku_id]["verified_at"] == "2026-08-16"


def test_seed_dry_run_reports_every_composition_without_writing():
    from backend.scripts.seed_stage2_verified_compositions import seed

    result = seed(commit=False)

    assert result["mode"] == "dry_run"
    assert len(result["compositions"]) == len(VERIFIED_COMPOSITIONS)
    assert {row["action"] for row in result["compositions"]} == {"would_upsert"}


def test_composition_version_is_stable():
    assert COMPOSITION_VERSION == "stage2-verified-composition-v1"
