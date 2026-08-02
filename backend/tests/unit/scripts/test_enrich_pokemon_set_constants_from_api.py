"""Targeted tests for backend/scripts/enrich_pokemon_set_constants_from_api.py.

build_local_inventory() walks the Pokemon constants root and imports a setMap
module per directory. Not every directory there is an era: scrape_job_reports/
holds generated JSON reports and has no setMap.py, which made the walk raise
ModuleNotFoundError before any enrichment could run.
"""

from backend.scripts import enrich_pokemon_set_constants_from_api as enrich


def test_directories_without_a_set_map_are_not_treated_as_eras(tmp_path, monkeypatch):
    root = tmp_path / "pokemon"

    # A real era name, so the import by module path resolves to the real package.
    era_dir = root / "otherEra"
    era_dir.mkdir(parents=True)
    (era_dir / "setMap.py").write_text("", encoding="utf-8")

    # Report output directory: a directory, not __pycache__, but with no setMap.py.
    (root / "scrape_job_reports").mkdir()
    (root / "scrape_job_reports" / "scrape_job_1.json").write_text("{}", encoding="utf-8")

    (root / "__pycache__").mkdir()

    monkeypatch.setattr(enrich, "POKEMON_ROOT", root)

    inventory = enrich.build_local_inventory()

    assert {row["era"] for row in inventory} == {"otherEra"}
    assert inventory, "the real otherEra setMap should still contribute set rows"


# ---------------------------------------------------------------------------
# Historical TCGplayer-only catalog review (dry-run reporting)
# ---------------------------------------------------------------------------
CATALOG_CONFIG = """from .baseConfig import BaseSetConfig


class SetExpeditionConfig(BaseSetConfig):
    SET_NAME = 'Expedition'
    SET_ID = None
    RELEASE_DATE = None
    TCGPLAYER_SET_ID = '1375'
    TCGPLAYER_SET_NAME = 'Expedition'
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1375/cards/?rows=5000&productTypeID=1'
"""

API_BY_ID = {
    "ecard1": {"id": "ecard1", "name": "Expedition Base Set", "total": 165},
    "base1": {"id": "base1", "name": "Base", "total": 102},
    "bw11": {"id": "bw11", "name": "Legendary Treasures", "total": 113},
}


def _review(key, config_text=CATALOG_CONFIG, internal_count=165):
    return enrich.build_catalog_review(
        canonical_key=key,
        config_text=config_text,
        api_by_id=API_BY_ID,
        internal_card_count=internal_count,
    )


def test_catalog_review_reports_every_required_field():
    review = _review("expedition")

    for field in (
        "canonical_key",
        "tcgplayer_set_id",
        "tcgplayer_set_name",
        "proposed_api_image_source_ids",
        "match_strategy",
        "mapping_kind",
        "expected_internal_card_count",
        "expected_api_card_count",
        "accepted",
        "reason",
    ):
        assert field in review, field


def test_one_to_one_catalog_is_accepted_with_its_reviewed_image_source():
    review = _review("expedition")

    assert review["mapping_kind"] == "one_to_one_api_match"
    assert review["proposed_api_image_source_ids"] == ["ecard1"]
    assert review["match_strategy"] == "confirmed_name_alias"
    assert review["accepted"] is True
    assert review["expected_internal_card_count"] == 165
    assert review["expected_api_card_count"] == 165
    assert review["tcgplayer_set_id"] == "1375"
    assert review["tcgplayer_set_name"] == "Expedition"


def test_parent_subset_catalog_is_reported_as_multi_or_parent():
    review = enrich.build_catalog_review(
        canonical_key="legendaryTreasuresRadiantCollection",
        config_text=CATALOG_CONFIG,
        api_by_id=API_BY_ID,
        internal_card_count=25,
    )

    assert review["mapping_kind"] == "multi_or_parent_api_mapping_required"
    assert review["proposed_api_image_source_ids"] == ["bw11"]
    assert review["expected_api_card_count"] == 113
    assert review["accepted"] is True


def test_mixed_catalog_is_rejected_with_its_explicit_reason():
    review = _review("battleAcademy", internal_count=138)

    assert review["mapping_kind"] == "no_api_equivalent"
    assert review["proposed_api_image_source_ids"] == []
    assert review["accepted"] is False
    assert "mixed" in review["reason"].lower()


def test_catalog_with_no_api_set_at_all_is_reported_as_unmapped():
    review = _review("xyTrainerKitLatiasAndLatios", internal_count=60)

    assert review["mapping_kind"] == "no_api_equivalent"
    assert review["proposed_api_image_source_ids"] == []
    assert review["accepted"] is False
    assert review["reason"]


def test_review_flags_drift_between_reviewed_and_live_internal_counts():
    review = _review("expedition", internal_count=99)

    assert review["accepted"] is False
    assert "drift" in review["reason"].lower()


def test_review_never_proposes_a_set_identity():
    # An image source must never be offered as SET_ID / pokemon_api_set_id.
    review = _review("expedition")

    assert "SET_ID" not in review
    assert "set_id" not in review
    assert "pokemon_api_set_id" not in review


def test_catalog_review_summary_counts_each_outcome():
    reviews = [
        _review("expedition"),
        enrich.build_catalog_review(
            canonical_key="baseSetShadowless", config_text=CATALOG_CONFIG,
            api_by_id=API_BY_ID, internal_card_count=102,
        ),
        _review("battleAcademy", internal_count=138),
        _review("xyTrainerKitLatiasAndLatios", internal_count=60),
    ]

    summary = enrich.summarize_catalog_reviews(reviews)

    assert summary["one_to_one_api_match"] == 1
    assert summary["multi_or_parent_api_mapping_required"] == 1
    assert summary["no_api_equivalent"] == 2
    assert summary["accepted_image_source_mappings"] == 2
