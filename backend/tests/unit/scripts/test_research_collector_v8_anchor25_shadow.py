from pathlib import Path

from backend.scripts.research_collector_v8_anchor25_shadow import (
    OVERALL_V8_SHADOW_VERSION,
    TEMPORAL_PASS,
    V8_VERSION,
    clamp,
    tier,
)


def test_v8_identity_is_anchor25_and_temporal_gated():
    assert V8_VERSION == "pokemon_collector_appeal_v8_anchor25_cross_domain_v1"
    assert OVERALL_V8_SHADOW_VERSION.endswith("collector_appeal_v8_anchor25")
    assert TEMPORAL_PASS == "ANCHOR25_TEMPORAL_VALIDATION_PASS"


def test_tier_thresholds_match_v12_contract():
    assert tier(90) == "S"
    assert tier(75) == "A"
    assert tier(55) == "B"
    assert tier(35) == "C"
    assert tier(15) == "D"
    assert tier(14.9999) == "F"


def test_clamp_is_bounded():
    assert clamp(-1) == 0
    assert clamp(50) == 50
    assert clamp(101) == 100


def test_shadow_harness_has_no_database_or_network_path():
    source = Path("backend/scripts/research_collector_v8_anchor25_shadow.py").read_text(encoding="utf-8").lower()
    for token in (".insert([", ".insert({", ".update({", ".delete()", ".upsert(", ".rpc(", ".table(", "execute_sql"):
        assert token not in source
    assert "supabase" not in source
    assert "requests" not in source
    assert "promotionperformed" in source


def test_frozen_overall_authority_is_exact_v12_cohort():
    import json
    path = Path("docs/research/collector_appeal/v8_anchor25_shadow/frozen_overall_v12_authority.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["authority"]["expectedRows"] == 276
    assert payload["authority"]["publicationRunId"] == "0f83d958-95aa-40f1-bcfa-ec550ec3a379"
    assert len(payload["rows"]) == 276
    assert len({row["id"] for row in payload["rows"]}) == 276
