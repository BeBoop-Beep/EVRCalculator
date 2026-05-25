import pandas as pd
import pytest
import inspect

from backend.constants.tcg.pokemon.megaEvolutionEra.ascendedHeroes import SetAscendedHeroesConfig
from backend.constants.tcg.pokemon.megaEvolutionEra.megaEvolution import SetMegaEvolutionConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.paldeaEvolved import SetPaldeaEvolvedConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.paldeanFates import SetPaldeanFatesConfig
from backend.constants.tcg.pokemon.sunAndMoonEra.burningShadows import SetBurningShadowsConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.brilliantStars import SetBrilliantStarsConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.simulations.evrSimulator import PackEVRSimulator, _should_use_monte_carlo_v2, get_simulation_engine
import backend.simulations.evrSimulator as evr_simulator_module


class _MegaNoFlag:
    ERA = "Mega Evolution"


class _SVFlagStringFalse:
    ERA = "Scarlet and Violet"
    USE_MONTE_CARLO_V2 = "false"


class _LegacyNoFlag:
    ERA = "Black and White"


class _ExplicitTrue:
    ERA = "Black and White"
    USE_MONTE_CARLO_V2 = True


class _ExplicitV2Engine:
    SIMULATION_ENGINE = "v2"


class _ExplicitSlotSchemaEngineNotEnabled:
    SIMULATION_ENGINE = "slot_schema"
    PULL_RATE_MAPPING = {"common": 1.0}
    RARE_SLOT_PROBABILITY = {"rare": 1.0}
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {"regular reverse": 1.0},
    }

    @classmethod
    def get_rarity_pack_multiplier(cls):
        return {"common": 4, "uncommon": 3}


class _ExplicitUnknownEngine:
    SIMULATION_ENGINE = "banana"


def test_should_use_monte_carlo_v2_true_for_explicit_flag():
    assert _should_use_monte_carlo_v2(_ExplicitTrue()) is True


def test_should_use_monte_carlo_v2_true_for_mega_and_sv_even_without_true_flag():
    assert _should_use_monte_carlo_v2(_MegaNoFlag()) is True
    assert _should_use_monte_carlo_v2(_SVFlagStringFalse()) is True


def test_should_use_monte_carlo_v2_false_for_legacy_era_without_flag():
    assert _should_use_monte_carlo_v2(_LegacyNoFlag()) is False


def test_current_scarlet_violet_sets_still_route_to_v2():
    for config in [SetPaldeaEvolvedConfig, SetPaldeanFatesConfig]:
        assert _should_use_monte_carlo_v2(config) is True
        assert get_simulation_engine(config) == "v2"


def test_current_mega_evolution_sets_still_route_to_v2():
    for config in [SetAscendedHeroesConfig, SetMegaEvolutionConfig]:
        assert _should_use_monte_carlo_v2(config) is True
        assert get_simulation_engine(config) == "v2"


def test_representative_real_sm_swsh_sets_are_not_routed_to_slot_schema():
    for config in [SetBurningShadowsConfig, SetBrilliantStarsConfig]:
        assert getattr(config, "SIMULATION_ENGINE", None) != "slot_schema"
        assert _should_use_monte_carlo_v2(config) is False
        assert get_simulation_engine(config) == "v1"


def test_chilling_reign_routes_to_slot_schema_pilot_engine():
    assert get_simulation_engine(SetChillingReignConfig) == "slot_schema"
    assert _should_use_monte_carlo_v2(SetChillingReignConfig) is False


def test_evolving_skies_routes_to_slot_schema_pilot_engine():
    assert get_simulation_engine(SetEvolvingSkiesConfig) == "slot_schema"
    assert _should_use_monte_carlo_v2(SetEvolvingSkiesConfig) is False


def test_configs_without_simulation_engine_preserve_legacy_routing():
    assert _should_use_monte_carlo_v2(_LegacyNoFlag()) is False
    assert get_simulation_engine(_LegacyNoFlag()) == "v1"


def test_explicit_v2_engine_routes_to_v2():
    assert get_simulation_engine(_ExplicitV2Engine()) == "v2"
    assert _should_use_monte_carlo_v2(_ExplicitV2Engine()) is True


def test_slot_schema_config_without_runtime_enabled_flag_fails_loudly():
    config = _ExplicitSlotSchemaEngineNotEnabled()
    assert get_simulation_engine(config) == "slot_schema"

    simulator = PackEVRSimulator(config)
    with pytest.raises(
        ValueError,
        match="SLOT_SCHEMA_RUNTIME_ENABLED",
    ):
        simulator.calculate_evr_simulations(pd.DataFrame())


def test_unknown_simulation_engine_fails_loudly():
    with pytest.raises(ValueError, match="Unsupported SIMULATION_ENGINE='banana'"):
        get_simulation_engine(_ExplicitUnknownEngine())


def test_evr_simulator_has_no_chilling_reign_specific_branches():
    source = inspect.getsource(evr_simulator_module).lower()
    assert "chilling reign" not in source
    assert "chilling_reign" not in source
