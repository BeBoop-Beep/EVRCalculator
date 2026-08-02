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
