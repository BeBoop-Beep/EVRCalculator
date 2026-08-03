"""Unit tests for the one-time historical TCGplayer catalog backfill service.

These cover the selection contract, deterministic URL derivation, the strict
Pokemon API match, catalog-only rendering, and canonical-key collision safety.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.services import pokemon_historical_catalog_backfill_service as svc


BASE_CONFIG_SOURCE = '''from types import MappingProxyType

class BaseSetConfig:
    COLLECTION = "TCG"
    TCG = "Pokemon"
    ERA = "Other"

    RARITY_MAPPING = MappingProxyType({
        "common": "common",
        "uncommon": "uncommon",
        "rare": "rare",
    })
'''

SET_MAP_SOURCE = """from .legendaryCollection import SetLegendaryCollectionConfig


SET_CONFIG_MAP = {
    'legendaryCollection' : SetLegendaryCollectionConfig,
}

SET_ALIAS_MAP = {
    "legendary collection": "legendaryCollection",
    "legendarycollection": "legendaryCollection",
}
"""

EXISTING_SET_SOURCE = """from .baseConfig import BaseSetConfig

class SetLegendaryCollectionConfig(BaseSetConfig):
    SET_NAME = 'Legendary Collection'
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PULL_RATE_MAPPING = {}
"""


def _baseline_row(**overrides):
    row = {
        "id": "job-1",
        "tcg": "pokemon",
        "source_system": "tcgplayer",
        "source_set_id": "1402",
        "source_set_name": "Shadowless Base Set",
        "status": "ignored",
        "current_step": "catalog_baseline",
        "metadata_json": {"onboarded": False, "baseline_reason": "captured during baseline"},
    }
    row.update(overrides)
    return row


def _pokemon_root(tmp_path: Path) -> Path:
    root = tmp_path / "pokemon"
    era = root / "otherEra"
    era.mkdir(parents=True)
    (era / "__init__.py").write_text("", encoding="utf-8")
    (era / "baseConfig.py").write_text(BASE_CONFIG_SOURCE, encoding="utf-8")
    (era / "setMap.py").write_text(SET_MAP_SOURCE, encoding="utf-8")
    (era / "legendaryCollection.py").write_text(EXISTING_SET_SOURCE, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# 1. Ignored baseline selection
# ---------------------------------------------------------------------------
def test_select_baseline_rows_accepts_only_unonboarded_ignored_catalog_baseline_rows():
    rows = [
        _baseline_row(source_set_id="1"),
        _baseline_row(source_set_id="2", status="detected"),
        _baseline_row(source_set_id="3", current_step="resolve_metadata"),
        _baseline_row(source_set_id="4", source_system="pokemon_api"),
        _baseline_row(source_set_id="5", metadata_json={"onboarded": True}),
    ]

    selected = svc.select_baseline_rows(rows)

    assert [row["source_set_id"] for row in selected] == ["1"]


def test_select_baseline_rows_filters_by_requested_source_set_ids_and_max_sets():
    rows = [_baseline_row(source_set_id=str(n), id=f"job-{n}") for n in range(1, 6)]

    assert [r["source_set_id"] for r in svc.select_baseline_rows(rows, source_set_ids=["3", "5"])] == ["3", "5"]
    assert [r["source_set_id"] for r in svc.select_baseline_rows(rows, max_sets=2)] == ["1", "2"]


# ---------------------------------------------------------------------------
# 10. Resume skips rows already completed by a previous execution
# ---------------------------------------------------------------------------
def test_select_baseline_rows_with_resume_skips_rows_whose_scrape_already_succeeded():
    done = _baseline_row(
        source_set_id="7",
        metadata_json={
            "onboarded": False,
            "historical_backfill": {"scrape_status": "success", "canonical_key": "shadowlessBaseSet"},
        },
    )
    pending = _baseline_row(source_set_id="8")

    assert [r["source_set_id"] for r in svc.select_baseline_rows([done, pending], resume=True)] == ["8"]
    assert [r["source_set_id"] for r in svc.select_baseline_rows([done, pending], resume=False)] == ["7", "8"]


# ---------------------------------------------------------------------------
# 2. Deterministic URL creation from source_set_id
# ---------------------------------------------------------------------------
def test_catalog_urls_are_derived_from_the_stored_provider_id_without_re_resolution():
    card_url, sealed_url = svc.catalog_urls("1402")

    assert card_url == "https://infinite-api.tcgplayer.com/priceguide/set/1402/cards/?rows=5000&productTypeID=1"
    assert sealed_url == "https://infinite-api.tcgplayer.com/priceguide/set/1402/cards/?rows=5000&productTypeID=25"
    assert svc.catalog_urls("1402") == svc.catalog_urls(1402)


def test_catalog_urls_rejects_a_non_numeric_provider_identity():
    with pytest.raises(svc.BackfillError):
        svc.catalog_urls("base-set")


# ---------------------------------------------------------------------------
# 3. Strict Pokemon API match
# ---------------------------------------------------------------------------
def test_strict_api_match_accepts_a_unique_exact_normalized_name():
    rows = [
        {"id": "base1", "name": "Base", "series": "Base", "releaseDate": "1999/01/09"},
        {"id": "base4", "name": "Base Set 2", "series": "Base", "releaseDate": "2000/02/24"},
    ]

    resolution = svc.resolve_api_match("Base", rows)

    assert resolution.status == "resolved"
    assert resolution.set_data["id"] == "base1"


def test_strict_api_match_refuses_ambiguous_or_fuzzy_catalog_names():
    duplicates = [
        {"id": "a", "name": "Trainer Kit", "series": "Base"},
        {"id": "b", "name": "Trainer Kit", "series": "EX"},
    ]
    assert svc.resolve_api_match("Trainer Kit", duplicates).status == "ambiguous"

    near_miss = [{"id": "c", "name": "Base Set (Shadowless)", "series": "Base"}]
    assert svc.resolve_api_match("Shadowless Base Set", near_miss).status != "resolved"


def test_explicit_mapping_is_empty_by_default_so_no_api_identity_is_ever_invented():
    assert svc.EXPLICIT_API_NAME_BY_SOURCE_SET_ID == {}


def test_explicit_mapping_redirects_the_lookup_name_but_still_requires_an_exact_match(monkeypatch):
    monkeypatch.setitem(svc.EXPLICIT_API_NAME_BY_SOURCE_SET_ID, "1375", "Expedition Base Set")

    assert svc.api_lookup_name_for("1375", "Expedition") == "Expedition Base Set"
    assert svc.api_lookup_name_for("9999", "Expedition") == "Expedition"

    rows = [{"id": "ecard1", "name": "Expedition Base Set", "series": "E-Card"}]
    assert svc.resolve_api_match(svc.api_lookup_name_for("1375", "Expedition"), rows).status == "resolved"
    # Without the mapping the provider label is not an exact API name, so it stays catalog-only.
    assert svc.resolve_api_match("Expedition", rows).status != "resolved"


def test_explicitly_mapped_row_generates_an_api_backed_config(tmp_path, monkeypatch):
    root = _pokemon_root(tmp_path)
    (root / "eCardEra").mkdir()
    (root / "eCardEra" / "baseConfig.py").write_text(BASE_CONFIG_SOURCE, encoding="utf-8")
    (root / "eCardEra" / "setMap.py").write_text(
        "SET_CONFIG_MAP = {\n}\n\nSET_ALIAS_MAP = {\n}\n", encoding="utf-8"
    )
    monkeypatch.setitem(svc.EXPLICIT_API_NAME_BY_SOURCE_SET_ID, "1375", "Expedition Base Set")
    api_rows = [{
        "id": "ecard1", "name": "Expedition Base Set", "series": "E-Card",
        "releaseDate": "2002/09/15", "printedTotal": 165, "total": 165,
        "ptcgoCode": None, "images": {},
    }]

    outcome = svc.generate_config_for_row(
        _baseline_row(source_set_id="1375", source_set_name="Expedition"),
        pokemon_root=root, api_rows=api_rows, taken_keys=set(), commit=True,
    )

    assert outcome.api_match_status == "resolved"
    assert outcome.era_folder == "eCardEra"
    assert outcome.pokemon_api_set_id == "ecard1"
    text = Path(outcome.config_path).read_text(encoding="utf-8")
    assert "SET_NAME = 'Expedition Base Set'" in text
    assert "TCGPLAYER_SET_NAME = 'Expedition'" in text


# ---------------------------------------------------------------------------
# 6. API-backed rows keep authoritative metadata but stay non-simulatable
# ---------------------------------------------------------------------------
def test_api_backed_config_uses_authoritative_metadata_and_preserves_provider_identity(tmp_path):
    root = _pokemon_root(tmp_path)
    (root / "baseWotcEra").mkdir()
    (root / "baseWotcEra" / "__init__.py").write_text("", encoding="utf-8")
    (root / "baseWotcEra" / "baseConfig.py").write_text(BASE_CONFIG_SOURCE, encoding="utf-8")
    (root / "baseWotcEra" / "setMap.py").write_text(
        "SET_CONFIG_MAP = {\n}\n\nSET_ALIAS_MAP = {\n}\n", encoding="utf-8"
    )
    api_rows = [{
        "id": "base1", "name": "Base", "series": "Base", "releaseDate": "1999/01/09",
        "printedTotal": 102, "total": 102, "ptcgoCode": None,
        "images": {"symbol": "https://images.pokemontcg.io/base1/symbol.png",
                   "logo": "https://images.pokemontcg.io/base1/logo.png"},
    }]

    outcome = svc.generate_config_for_row(
        _baseline_row(source_set_id="604", source_set_name="Base"),
        pokemon_root=root, api_rows=api_rows, taken_keys=set(), commit=True,
    )

    assert outcome.api_match_status == "resolved"
    assert outcome.era_folder == "baseWotcEra"
    assert outcome.pokemon_api_set_id == "base1"
    text = (root / "baseWotcEra" / f"{outcome.canonical_key}.py").read_text(encoding="utf-8")
    assert "SET_ID = 'base1'" in text
    assert "RELEASE_DATE = '1999/01/09'" in text
    assert "TCGPLAYER_SET_ID = '604'" in text
    assert "TCGPLAYER_SET_NAME = 'Base'" in text
    assert "CATALOG_ONLY = True" in text
    assert "SUPPORTS_OPENING_SIMULATION = False" in text
    assert "USE_MONTE_CARLO_V2 = False" in text
    assert 'PULL_MODEL_STATUS = "unsupported"' in text


# ---------------------------------------------------------------------------
# 4. No unique API match -> catalog-only config under otherEra
# ---------------------------------------------------------------------------
def test_unmatched_catalog_renders_a_catalog_only_config_without_inventing_metadata(tmp_path):
    root = _pokemon_root(tmp_path)

    outcome = svc.generate_config_for_row(
        _baseline_row(source_set_id="24688", source_set_name="Jumbo Cards"),
        pokemon_root=root, api_rows=[], taken_keys=set(), commit=True,
    )

    assert outcome.api_match_status == "not_found"
    assert outcome.era_folder == "otherEra"
    assert outcome.pokemon_api_set_id is None
    assert outcome.readiness == "ready_for_daily_scrape"

    text = Path(outcome.config_path).read_text(encoding="utf-8")
    assert "SET_ID = None" in text
    assert "TCGPLAYER_SET_ID = '24688'" in text
    assert "SET_NAME = 'Jumbo Cards'" in text
    assert "RELEASE_DATE = None" in text
    assert "SYMBOL_IMAGE_URL = None" in text
    assert "LOGO_IMAGE_URL = None" in text
    assert "CATALOG_ONLY = True" in text
    assert "SUPPORTS_OPENING_SIMULATION = False" in text
    assert "USE_MONTE_CARLO_V2 = False" in text
    assert "PULL_RATE_MAPPING = {}" in text
    assert 'PULL_MODEL_STATUS = "unsupported"' in text
    assert (
        "CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24688/cards/"
        "?rows=5000&productTypeID=1'"
    ) in text

    set_map_text = (root / "otherEra" / "setMap.py").read_text(encoding="utf-8")
    ast.parse(set_map_text)
    assert f"'{outcome.canonical_key}' : SetJumboCardsConfig," in set_map_text
    assert "from .jumboCards import SetJumboCardsConfig" in set_map_text


def test_api_lookup_failure_never_silently_downgrades_a_row_to_catalog_only(tmp_path):
    root = _pokemon_root(tmp_path)

    outcome = svc.generate_config_for_row(
        _baseline_row(source_set_id="24688", source_set_name="Jumbo Cards"),
        pokemon_root=root, api_rows=None, taken_keys=set(), commit=True,
    )

    assert outcome.api_match_status == "lookup_failed"
    assert outcome.error
    assert outcome.config_path is None
    assert not (root / "otherEra" / "jumboCards.py").exists()


# ---------------------------------------------------------------------------
# 5. Canonical-key collision
# ---------------------------------------------------------------------------
def test_colliding_canonical_name_gets_a_deterministic_provider_id_suffix(tmp_path):
    root = _pokemon_root(tmp_path)

    outcome = svc.generate_config_for_row(
        _baseline_row(source_set_id="7788", source_set_name="Legendary Collection"),
        pokemon_root=root, api_rows=[], taken_keys=svc.existing_canonical_keys(root), commit=True,
    )

    assert outcome.collision is True
    assert outcome.canonical_key == "legendaryCollectionTcg7788"
    assert (root / "otherEra" / "legendaryCollectionTcg7788.py").exists()


def test_allocate_canonical_key_is_deterministic_for_the_same_provider_id():
    taken = {"legendaryCollection"}
    first = svc.allocate_canonical_key("Legendary Collection", "7788", taken)
    second = svc.allocate_canonical_key("Legendary Collection", "7788", taken)

    assert first == second == ("legendaryCollectionTcg7788", True)
    assert svc.allocate_canonical_key("Jumbo Cards", "24688", taken) == ("jumboCards", False)


# ---------------------------------------------------------------------------
# 7. Existing configs are never overwritten
# ---------------------------------------------------------------------------
def test_existing_config_file_content_is_left_untouched(tmp_path):
    root = _pokemon_root(tmp_path)
    existing_path = root / "otherEra" / "legendaryCollection.py"
    before = existing_path.read_text(encoding="utf-8")

    svc.generate_config_for_row(
        _baseline_row(source_set_id="7788", source_set_name="Legendary Collection"),
        pokemon_root=root, api_rows=[], taken_keys=svc.existing_canonical_keys(root), commit=True,
    )

    assert existing_path.read_text(encoding="utf-8") == before


def test_dry_run_generation_writes_no_source_files(tmp_path):
    root = _pokemon_root(tmp_path)
    set_map_before = (root / "otherEra" / "setMap.py").read_text(encoding="utf-8")

    outcome = svc.generate_config_for_row(
        _baseline_row(source_set_id="24688", source_set_name="Jumbo Cards"),
        pokemon_root=root, api_rows=[], taken_keys=set(), commit=False,
    )

    assert outcome.canonical_key == "jumboCards"
    assert not (root / "otherEra" / "jumboCards.py").exists()
    assert (root / "otherEra" / "setMap.py").read_text(encoding="utf-8") == set_map_before


def test_invalid_generated_source_is_rolled_back_and_leaves_set_map_unchanged(tmp_path, monkeypatch):
    root = _pokemon_root(tmp_path)
    set_map_before = (root / "otherEra" / "setMap.py").read_text(encoding="utf-8")
    monkeypatch.setattr(
        svc, "render_catalog_only_config", lambda *a, **k: "class Broken(:\n    pass\n"
    )

    outcome = svc.generate_config_for_row(
        _baseline_row(source_set_id="24688", source_set_name="Jumbo Cards"),
        pokemon_root=root, api_rows=[], taken_keys=set(), commit=True,
    )

    assert outcome.error
    assert not (root / "otherEra" / "jumboCards.py").exists()
    assert (root / "otherEra" / "setMap.py").read_text(encoding="utf-8") == set_map_before


def test_config_whose_class_would_not_satisfy_the_set_map_import_is_rejected(tmp_path, monkeypatch):
    root = _pokemon_root(tmp_path)
    set_map_before = (root / "otherEra" / "setMap.py").read_text(encoding="utf-8")
    # Syntactically valid, but the class the setMap import line names is absent.
    monkeypatch.setattr(
        svc, "render_catalog_only_config", lambda *a, **k: "class SomethingElse:\n    pass\n"
    )

    outcome = svc.generate_config_for_row(
        _baseline_row(source_set_id="24688", source_set_name="Jumbo Cards"),
        pokemon_root=root, api_rows=[], taken_keys=set(), commit=True,
    )

    assert outcome.error
    assert not (root / "otherEra" / "jumboCards.py").exists()
    assert (root / "otherEra" / "setMap.py").read_text(encoding="utf-8") == set_map_before


# ---------------------------------------------------------------------------
# 15. Baseline job status handling
# ---------------------------------------------------------------------------
def test_partial_progress_keeps_the_row_ignored_and_unonboarded():
    row = _baseline_row()

    fields = svc.build_progress_fields(row, {"config_status": "generated", "scrape_status": "failed"})

    assert fields["status"] == "ignored"
    assert fields["current_step"] == "catalog_baseline"
    assert fields["metadata_json"]["onboarded"] is False
    assert fields["metadata_json"]["baseline_reason"] == "captured during baseline"
    assert fields["metadata_json"]["historical_backfill"]["scrape_status"] == "failed"
    assert "completed_at" not in fields


def test_full_success_marks_the_row_completed_while_preserving_baseline_history():
    row = _baseline_row()

    fields = svc.build_completion_fields(
        row, {"canonical_key": "jumboCards", "scrape_status": "success", "cards_written": 41}
    )

    assert fields["status"] == "completed"
    assert fields["current_step"] == "historical_scrape_complete"
    assert fields["metadata_json"]["onboarded"] is True
    assert fields["metadata_json"]["baseline_reason"] == "captured during baseline"
    assert fields["metadata_json"]["historical_backfill"]["canonical_key"] == "jumboCards"
    assert fields["completed_at"]


def test_failure_fields_never_use_a_worker_claimable_status():
    row = _baseline_row()

    fields = svc.build_progress_fields(row, {"scrape_status": "failed", "error": "boom"})

    assert fields["status"] not in {"detected", "ready", "retry", "running", "waiting"}
