import pytest

from backend.constants.tcg.pokemon.swordAndShieldEra.astralRadiance import SetAstralRadianceConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.battleStyles import SetBattleStylesConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.brilliantStars import SetBrilliantStarsConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.fusionStrike import SetFusionStrikeConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.lostOrigin import SetLostOriginConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.silverTempest import SetSilverTempestConfig
from backend.simulations.slotSchemaOutcomeResolver import validate_slot_schema_outcome_pool_mapping


LANE1_CONFIGS = {
    "swsh5": (
        SetBattleStylesConfig,
        "BATTLE_STYLES_PULL_RATE_REFERENCE_SOURCES",
        "BATTLE_STYLES_PULL_RATE_REFERENCE_BUCKET_EVIDENCE",
        "medium",
    ),
    "swsh9": (
        SetBrilliantStarsConfig,
        "BRILLIANT_STARS_PULL_RATE_REFERENCE_SOURCES",
        "BRILLIANT_STARS_PULL_RATE_REFERENCE_BUCKET_EVIDENCE",
        "medium_high",
    ),
    "swsh10": (
        SetAstralRadianceConfig,
        "ASTRAL_RADIANCE_PULL_RATE_REFERENCE_SOURCES",
        "ASTRAL_RADIANCE_PULL_RATE_REFERENCE_BUCKET_EVIDENCE",
        "high",
    ),
    "swsh11": (
        SetLostOriginConfig,
        "LOST_ORIGIN_PULL_RATE_REFERENCE_SOURCES",
        "LOST_ORIGIN_PULL_RATE_REFERENCE_BUCKET_EVIDENCE",
        "high",
    ),
    "swsh12": (
        SetSilverTempestConfig,
        "SILVER_TEMPEST_PULL_RATE_REFERENCE_SOURCES",
        "SILVER_TEMPEST_PULL_RATE_REFERENCE_BUCKET_EVIDENCE",
        "high",
    ),
}


def _lane1_cases():
    return [
        pytest.param(set_id, payload[0], payload[1], payload[2], payload[3], id=set_id)
        for set_id, payload in LANE1_CONFIGS.items()
    ]


def _assert_runtime_slot_schema_fields(config_cls):
    assert config_cls.SIMULATION_ENGINE == "slot_schema"
    assert config_cls.SLOT_SCHEMA_RUNTIME_ENABLED is True

    reverse = config_cls.REVERSE_SLOT_PROBABILITIES
    assert isinstance(reverse, dict)
    assert reverse
    for slot_name, slot_payload in reverse.items():
        assert slot_name
        assert isinstance(slot_payload, dict)
        assert slot_payload
        assert sum(float(v) for v in slot_payload.values()) == pytest.approx(1.0, abs=1e-12)

    table = config_cls.RARE_SLOT_PROBABILITY
    assert isinstance(table, dict)
    assert table
    assert "rare" in table
    assert all(float(value) >= 0.0 for value in table.values())
    assert sum(float(value) for value in table.values()) == pytest.approx(1.0, abs=1e-12)

    mapping = config_cls.SLOT_SCHEMA_OUTCOME_POOL_MAPPING
    assert isinstance(mapping, dict)
    assert set(mapping.keys()) == set(table.keys())
    validate_slot_schema_outcome_pool_mapping(config_cls)


@pytest.mark.parametrize("set_id,config_cls,sources_attr,evidence_attr,expected_confidence", _lane1_cases())
def test_lane1_runtime_fields_and_source_reference_presence(
    set_id,
    config_cls,
    sources_attr,
    evidence_attr,
    expected_confidence,
):
    _ = set_id
    _assert_runtime_slot_schema_fields(config_cls)

    confidence = config_cls.SLOT_SCHEMA_SOURCE_CONFIDENCE
    assert confidence["runtime_ready"] is True
    assert confidence["pool_mapping_ready"] is True
    assert confidence["rare_slot_probability_ready"] is True
    assert confidence["reverse_slot_probability_ready"] is True
    assert confidence["source_model"] == "best_available_empirical"

    sources = getattr(config_cls, sources_attr)
    evidence = getattr(config_cls, evidence_attr)

    assert isinstance(sources, list)
    assert len(sources) >= 3
    assert isinstance(evidence, list)
    assert len(evidence) > 0

    source_confidence_values = {str(row.get("source_confidence")) for row in sources}
    assert expected_confidence in source_confidence_values

    source_ids = {str(row.get("source_id")) for row in sources}
    assert any("thepricedex" in source_id for source_id in source_ids)


@pytest.mark.parametrize("set_id,config_cls,sources_attr,evidence_attr,expected_confidence", _lane1_cases())
def test_lane1_source_status_guardrails_for_secondary_and_unsupported_rows(
    set_id,
    config_cls,
    sources_attr,
    evidence_attr,
    expected_confidence,
):
    _ = (set_id, sources_attr, expected_confidence)
    evidence = getattr(config_cls, evidence_attr)

    for row in evidence:
        status = row.get("source_status")
        granularity = row.get("source_granularity_status")
        source_ids = [str(item) for item in (row.get("source_ids") or [])]
        normalized_bucket = str(row.get("normalized_bucket") or "").lower()
        bucket_label = str(row.get("source_bucket_label") or "").lower()

        assert status in {
            "SOURCE_DIRECT",
            "SOURCE_DERIVED_RESIDUAL",
            "PROVISIONAL_DIRECTIONAL",
            "UNSUPPORTED_SPLIT",
            "MISSING_SOURCE",
            "SECONDARY_INDEX_ONLY",
            "INFERRED_MODEL",
        }
        assert granularity in {
            "SOURCE_DIRECT",
            "SOURCE_DERIVED_RESIDUAL",
            "PROVISIONAL_DIRECTIONAL",
            "UNSUPPORTED_SPLIT",
            "MISSING_SOURCE",
            "SECONDARY_INDEX_ONLY",
            "INFERRED_MODEL",
        }

        if any("thepricedex" in source_id for source_id in source_ids):
            assert status == "SECONDARY_INDEX_ONLY"
            assert granularity == "SECONDARY_INDEX_ONLY"

        if "trainer gallery" in normalized_bucket or "unsupported" in bucket_label:
            assert status != "SOURCE_DIRECT"
            assert row.get("used_in_runtime") is False

        if "combined" in bucket_label or "hits per" in bucket_label:
            assert row.get("used_in_runtime") is False


@pytest.mark.parametrize("set_id,config_cls,sources_attr,evidence_attr,expected_confidence", _lane1_cases())
def test_lane1_runtime_taxonomy_does_not_mix_parent_and_child_overlapping_buckets(
    set_id,
    config_cls,
    sources_attr,
    evidence_attr,
    expected_confidence,
):
    _ = (set_id, sources_attr, evidence_attr, expected_confidence)
    keys = set(config_cls.RARE_SLOT_PROBABILITY.keys())

    # If broad full-art parent is present, child full-art split buckets must not also be runtime keys.
    if "full art" in keys:
        assert "full art v" not in keys
        assert "full art trainer" not in keys

    # If alternate art v is modeled, combined alt parent rows must remain reference-only.
    if "alternate art v" in keys:
        assert "alt v or vmax combined" not in keys


@pytest.mark.parametrize(
    "config_cls",
    [SetChillingReignConfig, SetEvolvingSkiesConfig, SetFusionStrikeConfig],
)
def test_swsh6_swsh7_swsh8_runtime_regression_guardrails(config_cls):
    assert config_cls.SIMULATION_ENGINE == "slot_schema"
    assert config_cls.SLOT_SCHEMA_RUNTIME_ENABLED is True

    table = config_cls.RARE_SLOT_PROBABILITY
    mapping = config_cls.SLOT_SCHEMA_OUTCOME_POOL_MAPPING
    reverse = config_cls.REVERSE_SLOT_PROBABILITIES

    assert isinstance(table, dict) and table
    assert isinstance(mapping, dict) and mapping
    assert isinstance(reverse, dict) and reverse

    assert set(mapping.keys()) == set(table.keys())
    assert sum(float(value) for value in table.values()) == pytest.approx(1.0, abs=1e-9)
