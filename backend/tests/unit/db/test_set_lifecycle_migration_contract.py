"""CI contract between lifecycle-changing SQL and the resolved Python registry."""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.db.services.pokemon_set_lifecycle_flags import resolve_config_lifecycle_flags
from backend.scripts.run_pokemon_set_scrape import build_valid_set_key_registry


MIGRATIONS = Path(__file__).resolve().parents[4] / "supabase" / "migrations"
CONTRACT_PREFIX = "-- pokemon-runtime-lifecycle-contract: "
TRACKED_COLUMNS = {
    "catalog_only",
    "ready_for_daily_scrape",
    "card_details_url",
    "has_card_details_url",
    "supports_opening_simulation",
    "parent_opening_set_id",
    "subset_type",
    "counts_toward_parent_set_value",
    "counts_toward_parent_opening",
}
ENFORCEMENT_START = "20260829005548"


def _contracts(sql: str) -> list[dict]:
    return [
        json.loads(line[len(CONTRACT_PREFIX):])
        for line in sql.splitlines()
        if line.startswith(CONTRACT_PREFIX)
    ]


def test_lifecycle_changing_migrations_declare_runtime_contracts():
    """A new migration cannot silently mutate a runtime-owned lifecycle field."""
    missing = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name[:14] < ENFORCEMENT_START:
            continue
        sql = path.read_text(encoding="utf-8")
        changes_lifecycle = bool(
            re.search(
                rf"\b(?:SET|ADD\s+COLUMN(?:\s+IF\s+NOT\s+EXISTS)?)\s+(?:{'|'.join(sorted(TRACKED_COLUMNS))})\b",
                sql,
                re.IGNORECASE,
            )
        )
        if changes_lifecycle and not _contracts(sql):
            missing.append(path.name)
    assert not missing, f"lifecycle migrations missing runtime contracts: {missing}"


def test_migration_contracts_equal_fully_resolved_registry_semantics():
    registry = build_valid_set_key_registry()["config_map"]
    mismatches = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name[:14] < ENFORCEMENT_START:
            continue
        for expected in _contracts(path.read_text(encoding="utf-8")):
            key = expected["canonical_key"]
            assert key in registry, f"{path.name}: unknown canonical key {key}"
            resolved = resolve_config_lifecycle_flags(registry[key])
            actual = {field: resolved[field] for field in expected if field != "canonical_key"}
            wanted = {field: value for field, value in expected.items() if field != "canonical_key"}
            if actual != wanted:
                mismatches.append({"migration": path.name, "key": key, "expected": wanted, "actual": actual})
    assert not mismatches, f"migration/runtime lifecycle divergence: {mismatches}"


def test_radiant_collections_are_daily_child_subsets_not_simulation_sets():
    registry = build_valid_set_key_registry()["config_map"]
    expected_parents = {
        "generationsRadiantCollection": "generations",
        "legendaryTreasuresRadiantCollection": "legendaryTreasures",
    }
    for key, parent_key in expected_parents.items():
        flags = resolve_config_lifecycle_flags(registry[key])
        assert flags["catalog_only"] is False
        assert flags["ready_for_daily_scrape"] is True
        assert flags["supports_opening_simulation"] is False
        assert flags["is_subset"] is True
        assert flags["parent_opening_set_key"] == parent_key
        assert flags["subset_type"] == "radiant_collection"
        assert flags["counts_toward_parent_set_value"] is True
        assert flags["counts_toward_parent_opening"] is True


def test_root_expansion_selection_is_structural_not_catalog_based():
    registry = build_valid_set_key_registry()["config_map"]
    roots = {
        key for key, config in registry.items()
        if not resolve_config_lifecycle_flags(config)["is_subset"]
    }
    assert "generationsRadiantCollection" not in roots
    assert "legendaryTreasuresRadiantCollection" not in roots
