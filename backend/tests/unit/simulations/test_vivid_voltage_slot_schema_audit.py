import pytest

from backend.constants.tcg.pokemon.swordAndShieldEra.battleStyles import SetBattleStylesConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.darknessAblaze import SetDarknessAblazeConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.fusionStrike import SetFusionStrikeConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.swordAndShield import SetSwordAndShieldConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.vividVoltage import SetVividVoltageConfig
from backend.simulations.slotSchemaOutcomeResolver import validate_slot_schema_outcome_pool_mapping


def test_vivid_voltage_runtime_slot_schema_contract():
    assert SetVividVoltageConfig.SIMULATION_ENGINE == "slot_schema"
    assert SetVividVoltageConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True

    rare_slot = SetVividVoltageConfig.RARE_SLOT_PROBABILITY
    reverse_slot = SetVividVoltageConfig.REVERSE_SLOT_PROBABILITIES
    mapping = SetVividVoltageConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING

    assert isinstance(rare_slot, dict) and rare_slot
    assert isinstance(reverse_slot, dict) and reverse_slot
    assert isinstance(mapping, dict) and mapping

    assert set(rare_slot.keys()) == set(mapping.keys())
    assert sum(float(v) for v in rare_slot.values()) == pytest.approx(1.0, abs=1e-9)
    for slot_payload in reverse_slot.values():
        assert sum(float(v) for v in slot_payload.values()) == pytest.approx(1.0, abs=1e-12)

    validate_slot_schema_outcome_pool_mapping(SetVividVoltageConfig)


def test_vivid_voltage_source_reference_metadata_and_policy_guards():
    confidence = SetVividVoltageConfig.SLOT_SCHEMA_SOURCE_CONFIDENCE
    assert confidence["runtime_ready"] is True
    assert confidence["pool_mapping_ready"] is True
    assert confidence["rare_slot_probability_ready"] is True
    assert confidence["reverse_slot_probability_ready"] is True
    assert "not official" in confidence["source_caveat"].lower()
    assert "digitaltq" in confidence["source_caveat"].lower()
    assert "thepricedex" in confidence["source_caveat"].lower()
    assert "amazing rare" in confidence["source_caveat"].lower()
    assert "conservative" in confidence["source_caveat"].lower()

    sources = SetVividVoltageConfig.VIVID_VOLTAGE_PULL_RATE_REFERENCE_SOURCES
    evidence = SetVividVoltageConfig.VIVID_VOLTAGE_PULL_RATE_REFERENCE_BUCKET_EVIDENCE

    assert isinstance(sources, list) and len(sources) >= 3
    assert isinstance(evidence, list) and len(evidence) > 0

    pricedex_rows = [
        row
        for row in evidence
        if any("thepricedex" in str(source_id).lower() for source_id in (row.get("source_ids") or []))
    ]
    assert pricedex_rows
    for row in pricedex_rows:
        assert row["source_status"] == "SECONDARY_INDEX_ONLY"
        assert row["source_granularity_status"] == "SECONDARY_INDEX_ONLY"
        assert row["used_in_runtime"] is False

    amazing_rare_rows = [
        row
        for row in evidence
        if str(row.get("normalized_bucket") or "").strip().lower() == "amazing rare"
    ]
    assert len(amazing_rare_rows) == 1
    amazing_rare_row = amazing_rare_rows[0]
    assert amazing_rare_row["source_status"] == "PROVISIONAL_DIRECTIONAL"
    assert amazing_rare_row["source_granularity_status"] == "PROVISIONAL_DIRECTIONAL"
    assert amazing_rare_row["used_in_runtime"] is False


@pytest.mark.parametrize(
    "forbidden_bucket",
    [
        "amazing rare",
        "trainer gallery",
        "radiant",
        "vstar",
        "regular vstar",
    ],
)
def test_vivid_voltage_runtime_excludes_forbidden_bucket_classes(forbidden_bucket):
    runtime_keys = {str(key).lower() for key in SetVividVoltageConfig.RARE_SLOT_PROBABILITY.keys()}
    mapping_keys = {str(key).lower() for key in SetVividVoltageConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys()}

    assert forbidden_bucket not in runtime_keys
    assert forbidden_bucket not in mapping_keys


@pytest.mark.parametrize(
    "config_cls",
    [
        SetSwordAndShieldConfig,
        SetDarknessAblazeConfig,
        SetBattleStylesConfig,
        SetFusionStrikeConfig,
    ],
)
def test_swsh_regression_runtime_contracts(config_cls):
    assert config_cls.SIMULATION_ENGINE == "slot_schema"
    assert config_cls.SLOT_SCHEMA_RUNTIME_ENABLED is True

    rare_slot = config_cls.RARE_SLOT_PROBABILITY
    reverse_slot = config_cls.REVERSE_SLOT_PROBABILITIES
    mapping = config_cls.SLOT_SCHEMA_OUTCOME_POOL_MAPPING

    assert isinstance(rare_slot, dict) and rare_slot
    assert isinstance(reverse_slot, dict) and reverse_slot
    assert isinstance(mapping, dict) and mapping

    assert set(rare_slot.keys()) == set(mapping.keys())
    assert sum(float(v) for v in rare_slot.values()) == pytest.approx(1.0, abs=1e-9)
