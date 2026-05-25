import pytest

from backend.constants.tcg.pokemon.sunAndMoonEra.baseConfig import BaseSetConfig as SunAndMoonBaseSetConfig
from backend.constants.tcg.pokemon.sunAndMoonEra.burningShadows import SetBurningShadowsConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.baseConfig import BaseSetConfig as SwordAndShieldBaseSetConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.brilliantStars import SetBrilliantStarsConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.celebrations import SetCelebrationsConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.jobs.evr_runner import _build_constants_config_map
from backend.simulations.evrSimulator import _should_use_monte_carlo_v2, get_simulation_engine
from backend.simulations.slotSchemaContract import compute_total_modeled_slots, validate_slot_schema_config


def _assert_standard_pre_sv_shape(base_config):
    summary = validate_slot_schema_config(base_config)
    assert summary["common_slots"] == 5
    assert summary["uncommon_slots"] == 3
    assert summary["rare_family_slot_count"] == 2
    assert summary["total_modeled_slots"] == 10

    assert base_config.SLOTS_PER_RARITY == {
        "common": 5,
        "uncommon": 3,
        "reverse": 1,
        "rare": 1,
    }
    assert compute_total_modeled_slots(base_config.PACK_STRUCTURE) == 10


def test_sun_and_moon_base_config_exposes_standard_pre_sv_pack_structure():
    _assert_standard_pre_sv_shape(SunAndMoonBaseSetConfig)


def test_sword_and_shield_base_config_exposes_standard_pre_sv_pack_structure():
    _assert_standard_pre_sv_shape(SwordAndShieldBaseSetConfig)


def test_representative_real_sets_inherit_standard_pre_sv_pack_structure():
    for config in [SetBurningShadowsConfig, SetBrilliantStarsConfig, SetChillingReignConfig, SetEvolvingSkiesConfig]:
        assert config.PACK_STRUCTURE == SwordAndShieldBaseSetConfig.PACK_STRUCTURE or config.PACK_STRUCTURE == SunAndMoonBaseSetConfig.PACK_STRUCTURE
        assert compute_total_modeled_slots(config.PACK_STRUCTURE) == 10


def test_chilling_reign_slot_schema_route_is_configured_but_runtime_disabled_until_tables_exist():
    assert getattr(SetChillingReignConfig, "SIMULATION_ENGINE", None) == "slot_schema"
    assert getattr(SetChillingReignConfig, "SLOT_SCHEMA_RUNTIME_ENABLED", True) is False
    assert get_simulation_engine(SetChillingReignConfig) == "slot_schema"


def test_evolving_skies_slot_schema_route_is_configured_but_runtime_disabled_until_tables_exist():
    assert getattr(SetEvolvingSkiesConfig, "SIMULATION_ENGINE", None) == "slot_schema"
    assert getattr(SetEvolvingSkiesConfig, "SLOT_SCHEMA_RUNTIME_ENABLED", True) is False
    assert get_simulation_engine(SetEvolvingSkiesConfig) == "slot_schema"


def test_evolving_skies_pack_structure_contract_is_standard_swsh_5311_total_10():
    summary = validate_slot_schema_config(SetEvolvingSkiesConfig)
    assert summary["common_slots"] == 5
    assert summary["uncommon_slots"] == 3
    assert summary["rare_family_slot_count"] == 2
    assert summary["total_modeled_slots"] == 10


def test_chilling_reign_pack_structure_contract_is_standard_swsh_5311_total_10():
    summary = validate_slot_schema_config(SetChillingReignConfig)
    assert summary["common_slots"] == 5
    assert summary["uncommon_slots"] == 3
    assert summary["rare_family_slot_count"] == 2
    assert summary["total_modeled_slots"] == 10


def test_chilling_reign_pack_structure_has_exactly_one_reverse_and_one_rare_family_slot():
    structure = SetChillingReignConfig.PACK_STRUCTURE
    rare_family_slots = structure["rare_family_slots"]

    reverse_like_roles = {"reverse_parallel", "reverse_subset"}
    reverse_slot_count = sum(1 for slot in rare_family_slots if slot.get("role") in reverse_like_roles)
    rare_or_better_slot_count = sum(1 for slot in rare_family_slots if slot.get("role") == "rare_or_better")

    assert structure["common_slots"] == 5
    assert structure["uncommon_slots"] == 3
    assert reverse_slot_count == 1
    assert rare_or_better_slot_count == 1


def test_chilling_reign_does_not_use_sv_mega_v2_reverse1_reverse2_rare_state_shape():
    rare_family_slots = SetChillingReignConfig.PACK_STRUCTURE["rare_family_slots"]
    slot_names = {slot.get("name") for slot in rare_family_slots}

    assert _should_use_monte_carlo_v2(SetChillingReignConfig) is False
    assert slot_names != {"reverse_1", "reverse_2", "rare"}


def test_celebrations_is_documented_as_future_special_override_before_slot_schema_routing():
    # Celebrations has a known special product structure (4-card behavior) and must
    # receive an explicit four-card PACK_STRUCTURE override before slot-schema
    # routing is enabled in production.
    # This test intentionally locks current safety: no slot-schema engine routing yet.
    assert get_simulation_engine(SetCelebrationsConfig) == "v1"
    assert getattr(SetCelebrationsConfig, "SIMULATION_ENGINE", None) != "slot_schema"
    assert compute_total_modeled_slots(SetCelebrationsConfig.PACK_STRUCTURE) == 10


def test_celebrations_cannot_use_inherited_standard_structure_with_slot_schema_engine():
    class _CelebrationsSlotSchemaAttempt(SetCelebrationsConfig):
        SIMULATION_ENGINE = "slot_schema"

    with pytest.raises(ValueError, match="four-card override"):
        get_simulation_engine(_CelebrationsSlotSchemaAttempt)


def test_evr_runner_config_discovery_excludes_blocked_slot_schema_pilot_sets():
    config_map = _build_constants_config_map()

    # Current EVR runner discovery is intentionally restricted to SV/Mega maps,
    # so blocked slot-schema pilots are not runtime/backfill candidates.
    assert "chillingReign" not in config_map
