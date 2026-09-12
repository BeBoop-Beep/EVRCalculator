from datetime import date
from pathlib import Path

from backend.scripts.build_index_fair_value_research_dataset import (
    MODEL_RUN_ID,
    MODEL_VERSION,
    TAXONOMY_VERSION,
    _days_old,
    canonical_hash,
)


def test_frozen_authority_bindings() -> None:
    assert MODEL_VERSION == "pokemon_collector_appeal_v7_expanded_price_blind_v1"
    assert MODEL_RUN_ID == "e282f26e-2136-4105-b0a3-f0974c4d9d70"
    assert TAXONOMY_VERSION == "pokemon_card_treatment_taxonomy_v3"


def test_dataset_fingerprint_is_order_and_run_sensitive() -> None:
    left = canonical_hash({"run": MODEL_RUN_ID, "rows": [{"id": "a", "price": 1.0}]})
    right = canonical_hash({"rows": [{"price": 1.0, "id": "a"}], "run": MODEL_RUN_ID})
    changed = canonical_hash({"run": "different", "rows": [{"id": "a", "price": 1.0}]})
    assert left == right
    assert left != changed


def test_release_age_is_as_of_bound() -> None:
    assert _days_old("2026-09-01", date(2026, 9, 11)) == 10
    assert _days_old(None, date(2026, 9, 11)) is None


def test_builder_has_no_database_mutation_calls() -> None:
    source = Path("backend/scripts/build_index_fair_value_research_dataset.py").read_text(encoding="utf-8")
    for forbidden in (".insert({", ".upsert(", ").update(", ").delete(", ".rpc("):
        assert forbidden not in source
