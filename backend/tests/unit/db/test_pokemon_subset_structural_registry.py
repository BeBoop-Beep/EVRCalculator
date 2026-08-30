from backend.db.services.opening_simulation_gate import supported_opening_set_keys
from backend.db.services.pokemon_set_lifecycle_flags import resolve_config_lifecycle_flags
from backend.scripts.run_pokemon_set_scrape import build_valid_set_key_registry


EXPECTED_SUBSETS = {
    "astralRadianceTrainerGallery": ("astralRadiance", "trainer_gallery"),
    "brilliantStarsTrainerGallery": ("brilliantStars", "trainer_gallery"),
    "celebrationsClassicCollection": ("celebrations", "classic_collection"),
    "crownZenithGalarianGallery": ("crownZenith", "galarian_gallery"),
    "hiddenFatesShinyVault": ("hiddenFates", "shiny_vault"),
    "lostOriginTrainerGallery": ("lostOrigin", "trainer_gallery"),
    "shiningFatesShinyVault": ("shiningFates", "shiny_vault"),
    "silverTempestTrainerGallery": ("silverTempest", "trainer_gallery"),
}


def test_child_subset_structural_metadata_matches_canonical_contract():
    configs = build_valid_set_key_registry()["config_map"]
    for key, (parent, subset_type) in EXPECTED_SUBSETS.items():
        flags = resolve_config_lifecycle_flags(configs[key])
        assert flags == {
            **flags,
            "parent_canonical_key": parent,
            "is_subset": True,
            "subset_type": subset_type,
            "counts_toward_parent_set_value": True,
            "counts_toward_parent_opening": True,
            "catalog_only": False,
            "ready_for_daily_scrape": True,
            "supports_opening_simulation": False,
        }


def test_child_subsets_are_not_independent_opening_roots():
    supported = set(supported_opening_set_keys())
    assert supported.isdisjoint(EXPECTED_SUBSETS)
    assert len(supported) == 22
