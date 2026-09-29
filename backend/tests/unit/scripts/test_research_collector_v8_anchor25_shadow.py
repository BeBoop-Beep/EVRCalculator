from pathlib import Path

from backend.scripts.research_collector_v8_anchor25_shadow import (
    ALPHA,
    TEMPORAL_DECISION,
    TEMPORAL_SHA,
    V8_SHADOW_VERSION,
    tie_percentiles,
)


def test_shadow_authority_is_pinned():
    assert ALPHA == 0.25
    assert TEMPORAL_DECISION == "ANCHOR25_TEMPORAL_VALIDATION_PASS"
    assert TEMPORAL_SHA == "26dde672086cfc429e9b4ca2a48062badc91a8ea"
    assert V8_SHADOW_VERSION == "pokemon_collector_appeal_v8_anchor25_cross_domain_shadow_v1"


def test_tie_percentiles_are_midrank_and_monotone():
    result = tie_percentiles({"a": 1.0, "b": 1.0, "c": 3.0})
    assert result["a"] == result["b"]
    assert result["a"] < result["c"]


def test_shadow_harness_has_no_database_write_tokens():
    source = Path("backend/scripts/research_collector_v8_anchor25_shadow.py").read_text(encoding="utf-8").lower()
    for token in (".insert(", ".update(", ".delete(", ".upsert(", ".rpc(", "execute_sql", "apply_migration"):
        assert token not in source
    assert "pokemon_overall_rip_current_publication" in source
    assert "pokemon_overall_rip_publication_rows" in source
