import pytest

from backend.constants.tcg.pokemon.swordAndShieldEra.battleStyles import SetBattleStylesConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.darknessAblaze import SetDarknessAblazeConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.fusionStrike import SetFusionStrikeConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.rebelClash import SetRebelClashConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.swordAndShield import SetSwordAndShieldConfig
from backend.simulations.slotSchemaOutcomeResolver import validate_slot_schema_outcome_pool_mapping


EARLY_REGULAR_CONFIGS = {
    "swsh1": (
        SetSwordAndShieldConfig,
        "SWORD_AND_SHIELD_PULL_RATE_REFERENCE_SOURCES",
        "SWORD_AND_SHIELD_PULL_RATE_REFERENCE_BUCKET_EVIDENCE",
    ),
    "swsh2": (
        SetRebelClashConfig,
        "REBEL_CLASH_PULL_RATE_REFERENCE_SOURCES",
        "REBEL_CLASH_PULL_RATE_REFERENCE_BUCKET_EVIDENCE",
    ),
    "swsh3": (
        SetDarknessAblazeConfig,
        "DARKNESS_ABLAZE_PULL_RATE_REFERENCE_SOURCES",
        "DARKNESS_ABLAZE_PULL_RATE_REFERENCE_BUCKET_EVIDENCE",
    ),
}


def _cases():
    return [
        pytest.param(set_id, payload[0], payload[1], payload[2], id=set_id)
        for set_id, payload in EARLY_REGULAR_CONFIGS.items()
    ]


def _assert_runtime_slot_schema_fields(config_cls):
    assert config_cls.SIMULATION_ENGINE == "slot_schema"
    assert config_cls.SLOT_SCHEMA_RUNTIME_ENABLED is True

    reverse = config_cls.REVERSE_SLOT_PROBABILITIES
    assert isinstance(reverse, dict)
    assert reverse
    for slot_payload in reverse.values():
        assert isinstance(slot_payload, dict)
        assert slot_payload
        assert sum(float(v) for v in slot_payload.values()) == pytest.approx(1.0, abs=1e-12)

    rare_slot_table = config_cls.RARE_SLOT_PROBABILITY
    assert isinstance(rare_slot_table, dict)
    assert rare_slot_table
    assert set(rare_slot_table.keys()) == set(config_cls.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())
    assert sum(float(v) for v in rare_slot_table.values()) == pytest.approx(1.0, abs=1e-12)
    assert all(float(v) >= 0.0 for v in rare_slot_table.values())

    validate_slot_schema_outcome_pool_mapping(config_cls)


@pytest.mark.parametrize("set_id,config_cls,sources_attr,evidence_attr", _cases())
def test_early_regular_runtime_slot_schema_contract(
    set_id,
    config_cls,
    sources_attr,
    evidence_attr,
):
    _ = set_id
    _assert_runtime_slot_schema_fields(config_cls)

    confidence = config_cls.SLOT_SCHEMA_SOURCE_CONFIDENCE
    assert confidence["runtime_ready"] is True
    assert confidence["pool_mapping_ready"] is True
    assert confidence["rare_slot_probability_ready"] is True
    assert confidence["reverse_slot_probability_ready"] is True

    sources = getattr(config_cls, sources_attr)
    evidence = getattr(config_cls, evidence_attr)

    assert isinstance(sources, list)
    assert len(sources) >= 3
    assert isinstance(evidence, list)
    assert len(evidence) > 0


@pytest.mark.parametrize("set_id,config_cls,sources_attr,evidence_attr", _cases())
def test_early_regular_source_status_and_unsupported_guardrails(
    set_id,
    config_cls,
    sources_attr,
    evidence_attr,
):
    _ = (set_id, sources_attr)
    evidence = getattr(config_cls, evidence_attr)

    for row in evidence:
        status = str(row.get("source_status") or "")
        granularity = str(row.get("source_granularity_status") or "")
        source_ids = [str(item) for item in (row.get("source_ids") or [])]
        normalized_bucket = str(row.get("normalized_bucket") or "").lower()

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

        if any("thepricedex" in source_id.lower() for source_id in source_ids):
            assert status == "SECONDARY_INDEX_ONLY"
            assert granularity == "SECONDARY_INDEX_ONLY"
            assert row.get("used_in_runtime") is False

        if status in {
            "MISSING_SOURCE",
            "UNSUPPORTED_SPLIT",
            "SECONDARY_INDEX_ONLY",
            "INFERRED_MODEL",
            "PROVISIONAL_DIRECTIONAL",
        }:
            assert row.get("used_in_runtime") is False

        if any(token in normalized_bucket for token in ("amazing rare", "trainer gallery", "radiant", "vstar")):
            assert row.get("used_in_runtime") is False


@pytest.mark.parametrize("set_id,config_cls,sources_attr,evidence_attr", _cases())
def test_early_regular_runtime_bucket_scope_excludes_out_of_scope_taxonomy(
    set_id,
    config_cls,
    sources_attr,
    evidence_attr,
):
    _ = (set_id, sources_attr, evidence_attr)
    keys = {str(key).lower() for key in config_cls.RARE_SLOT_PROBABILITY.keys()}

    forbidden = {
        "amazing rare",
        "trainer gallery",
        "radiant",
        "vstar",
        "regular vstar",
        "full art trainer",
        "full art pokemon",
        "alternate art v",
        "alternate art vmax",
    }

    assert forbidden.isdisjoint(keys)


@pytest.mark.parametrize("config_cls", [SetBattleStylesConfig, SetFusionStrikeConfig])
def test_swsh5_swsh8_regression_contract_stays_valid(config_cls):
    assert config_cls.SIMULATION_ENGINE == "slot_schema"
    assert config_cls.SLOT_SCHEMA_RUNTIME_ENABLED is True

    rare_slot_table = config_cls.RARE_SLOT_PROBABILITY
    reverse = config_cls.REVERSE_SLOT_PROBABILITIES
    mapping = config_cls.SLOT_SCHEMA_OUTCOME_POOL_MAPPING

    assert isinstance(rare_slot_table, dict) and rare_slot_table
    assert isinstance(reverse, dict) and reverse
    assert isinstance(mapping, dict) and mapping

    assert set(rare_slot_table.keys()) == set(mapping.keys())
    assert sum(float(value) for value in rare_slot_table.values()) == pytest.approx(1.0, abs=1e-9)
