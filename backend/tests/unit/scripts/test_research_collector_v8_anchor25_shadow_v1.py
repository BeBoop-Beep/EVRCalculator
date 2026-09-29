from pathlib import Path

from backend.scripts.research_collector_v8_anchor25_shadow_v1 import (
    ALPHA,
    CANDIDATE,
    OVERALL_WEIGHTS,
    V8_VERSION,
)


def test_v8_shadow_contract_is_frozen():
    assert CANDIDATE == "ANCHOR25"
    assert ALPHA == 0.25
    assert OVERALL_WEIGHTS == {"financial": 0.86, "chase": 0.04, "collector": 0.10}
    assert V8_VERSION == "pokemon_collector_appeal_v8_anchor25_cross_domain_shadow_v1"


def test_v8_shadow_has_no_database_write_calls():
    source = Path("backend/scripts/research_collector_v8_anchor25_shadow_v1.py").read_text(encoding="utf-8").lower()
    for token in (".insert(", ".update(", ".delete(", ".upsert(", "apply_migration", "promote_"):
        assert token not in source
    assert ".rpc(" not in source


def test_v8_shadow_requires_temporal_pass_and_v7_replay():
    source = Path("backend/scripts/research_collector_v8_anchor25_shadow_v1.py").read_text(encoding="utf-8")
    assert 'ANCHOR25_TEMPORAL_VALIDATION_PASS' in source
    assert 'V8_SHADOW_V7_SET_REPLAY_FAILED' in source
    assert 'V8_SHADOW_V12_COMPONENT_REPLAY_FAILED' in source
