import numpy as np

from backend.constants.tcg.pokemon.megaEvolutionEra.ascendedHeroes import SetAscendedHeroesConfig
from backend.constants.tcg.pokemon.megaEvolutionEra.baseConfig import BaseSetConfig as MegaEvolutionBaseSetConfig
from backend.constants.tcg.pokemon.megaEvolutionEra.megaEvolution import SetMegaEvolutionConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.baseConfig import BaseSetConfig as ScarletVioletBaseSetConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.paldeaEvolved import SetPaldeaEvolvedConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.paldeanFates import SetPaldeanFatesConfig
from backend.simulations.evrSimulator import _should_use_monte_carlo_v2
from backend.simulations.monteCarloSimV2 import sample_pack_state
from backend.simulations.utils.packStateModels.packStateModelOrchestrator import resolve_pack_state_model


def test_scarlet_violet_base_config_contract_remains_stable():
    assert ScarletVioletBaseSetConfig.ERA == "Scarlet and Violet"
    assert ScarletVioletBaseSetConfig.SLOTS_PER_RARITY == {
        "common": 4,
        "uncommon": 3,
        "reverse": 2,
        "rare": 1,
    }

    if hasattr(ScarletVioletBaseSetConfig, "USE_MONTE_CARLO_V2"):
        assert ScarletVioletBaseSetConfig.USE_MONTE_CARLO_V2 is True

    assert callable(ScarletVioletBaseSetConfig.get_reverse_eligible_rarities)
    assert isinstance(ScarletVioletBaseSetConfig.get_reverse_eligible_rarities(), list)

    assert callable(ScarletVioletBaseSetConfig.get_pack_state_overrides)
    assert isinstance(ScarletVioletBaseSetConfig.get_pack_state_overrides(), dict)

    etb_rules = ScarletVioletBaseSetConfig.PRODUCT_VARIANT_RULES["etb"]
    assert etb_rules["standard"]["packs_per_product"] == 9
    assert etb_rules["pokemon_center"]["packs_per_product"] == 11


def test_mega_evolution_base_config_contract_remains_stable():
    assert MegaEvolutionBaseSetConfig.ERA == "Mega Evolution"
    assert MegaEvolutionBaseSetConfig.SLOTS_PER_RARITY == {
        "common": 4,
        "uncommon": 3,
        "reverse": 2,
        "rare": 1,
    }

    if hasattr(MegaEvolutionBaseSetConfig, "USE_MONTE_CARLO_V2"):
        assert MegaEvolutionBaseSetConfig.USE_MONTE_CARLO_V2 is True

    if hasattr(MegaEvolutionBaseSetConfig, "get_reverse_eligible_rarities"):
        assert callable(MegaEvolutionBaseSetConfig.get_reverse_eligible_rarities)
        assert isinstance(MegaEvolutionBaseSetConfig.get_reverse_eligible_rarities(), list)

    if hasattr(MegaEvolutionBaseSetConfig, "get_pack_state_overrides"):
        assert callable(MegaEvolutionBaseSetConfig.get_pack_state_overrides)
        assert isinstance(MegaEvolutionBaseSetConfig.get_pack_state_overrides(), dict)


def test_paldea_evolved_contract_keeps_reverse_and_rare_probability_tables():
    assert issubclass(SetPaldeaEvolvedConfig, ScarletVioletBaseSetConfig)
    assert isinstance(SetPaldeaEvolvedConfig.PULL_RATE_MAPPING, dict)
    assert isinstance(SetPaldeaEvolvedConfig.REVERSE_SLOT_PROBABILITIES, dict)
    assert isinstance(SetPaldeaEvolvedConfig.RARE_SLOT_PROBABILITY, dict)

    assert "slot_1" in SetPaldeaEvolvedConfig.REVERSE_SLOT_PROBABILITIES
    assert "slot_2" in SetPaldeaEvolvedConfig.REVERSE_SLOT_PROBABILITIES
    assert "regular reverse" in SetPaldeaEvolvedConfig.REVERSE_SLOT_PROBABILITIES["slot_1"]
    assert "regular reverse" in SetPaldeaEvolvedConfig.REVERSE_SLOT_PROBABILITIES["slot_2"]
    assert "illustration rare" in SetPaldeaEvolvedConfig.REVERSE_SLOT_PROBABILITIES["slot_2"]
    assert "special illustration rare" in SetPaldeaEvolvedConfig.REVERSE_SLOT_PROBABILITIES["slot_2"]
    assert "hyper rare" in SetPaldeaEvolvedConfig.REVERSE_SLOT_PROBABILITIES["slot_2"]

    assert "rare" in SetPaldeaEvolvedConfig.RARE_SLOT_PROBABILITY
    assert "double rare" in SetPaldeaEvolvedConfig.RARE_SLOT_PROBABILITY
    assert "ultra rare" in SetPaldeaEvolvedConfig.RARE_SLOT_PROBABILITY


def test_paldean_fates_contract_keeps_special_reverse_outcomes_and_rare_table():
    assert issubclass(SetPaldeanFatesConfig, ScarletVioletBaseSetConfig)
    assert isinstance(SetPaldeanFatesConfig.PULL_RATE_MAPPING, dict)
    assert isinstance(SetPaldeanFatesConfig.REVERSE_SLOT_PROBABILITIES, dict)
    assert isinstance(SetPaldeanFatesConfig.RARE_SLOT_PROBABILITY, dict)

    assert "slot_1" in SetPaldeanFatesConfig.REVERSE_SLOT_PROBABILITIES
    assert "slot_2" in SetPaldeanFatesConfig.REVERSE_SLOT_PROBABILITIES
    assert "shiny rare" in SetPaldeanFatesConfig.REVERSE_SLOT_PROBABILITIES["slot_1"]
    assert "shiny ultra rare" in SetPaldeanFatesConfig.REVERSE_SLOT_PROBABILITIES["slot_1"]
    assert "regular reverse" in SetPaldeanFatesConfig.REVERSE_SLOT_PROBABILITIES["slot_1"]
    assert "regular reverse" in SetPaldeanFatesConfig.REVERSE_SLOT_PROBABILITIES["slot_2"]

    assert "rare" in SetPaldeanFatesConfig.RARE_SLOT_PROBABILITY
    assert "double rare" in SetPaldeanFatesConfig.RARE_SLOT_PROBABILITY
    assert "ultra rare" in SetPaldeanFatesConfig.RARE_SLOT_PROBABILITY


def test_ascended_heroes_contract_keeps_v2_probabilities_and_overrides_shape():
    assert SetAscendedHeroesConfig.ERA == "Mega Evolution"
    assert _should_use_monte_carlo_v2(SetAscendedHeroesConfig) is True
    assert isinstance(SetAscendedHeroesConfig.PULL_RATE_MAPPING, dict)
    assert isinstance(SetAscendedHeroesConfig.REVERSE_SLOT_PROBABILITIES, dict)
    assert isinstance(SetAscendedHeroesConfig.RARE_SLOT_PROBABILITY, dict)
    assert "slot_1" in SetAscendedHeroesConfig.REVERSE_SLOT_PROBABILITIES
    assert "slot_2" in SetAscendedHeroesConfig.REVERSE_SLOT_PROBABILITIES

    overrides = SetAscendedHeroesConfig.get_pack_state_overrides()
    assert isinstance(overrides, dict)

    assert SetAscendedHeroesConfig.GOD_PACK_CONFIG["enabled"] is True
    assert SetAscendedHeroesConfig.GOD_PACK_CONFIG["pull_rate"] == 1 / 2000
    assert SetAscendedHeroesConfig.GOD_PACK_CONFIG["strategy"]["type"] == "random"
    assert SetAscendedHeroesConfig.DEMI_GOD_PACK_CONFIG["enabled"] is False


def test_mega_evolution_set_contract_keeps_v2_probabilities_and_overrides_shape():
    assert SetMegaEvolutionConfig.ERA == "Mega Evolution"
    assert _should_use_monte_carlo_v2(SetMegaEvolutionConfig) is True
    assert isinstance(SetMegaEvolutionConfig.PULL_RATE_MAPPING, dict)
    assert isinstance(SetMegaEvolutionConfig.REVERSE_SLOT_PROBABILITIES, dict)
    assert isinstance(SetMegaEvolutionConfig.RARE_SLOT_PROBABILITY, dict)
    assert "slot_1" in SetMegaEvolutionConfig.REVERSE_SLOT_PROBABILITIES
    assert "slot_2" in SetMegaEvolutionConfig.REVERSE_SLOT_PROBABILITIES

    overrides = SetMegaEvolutionConfig.get_pack_state_overrides()
    assert isinstance(overrides, dict)


def test_engine_routing_remains_v2_for_current_sv_and_mega_sets():
    assert _should_use_monte_carlo_v2(SetPaldeaEvolvedConfig) is True
    assert _should_use_monte_carlo_v2(SetPaldeanFatesConfig) is True
    assert _should_use_monte_carlo_v2(SetAscendedHeroesConfig) is True
    assert _should_use_monte_carlo_v2(SetMegaEvolutionConfig) is True

    for cfg in [
        SetPaldeaEvolvedConfig,
        SetPaldeanFatesConfig,
        SetAscendedHeroesConfig,
        SetMegaEvolutionConfig,
    ]:
        assert not hasattr(cfg, "PACK_STRUCTURE")
        assert not hasattr(cfg, "SIMULATION_ENGINE")
        assert not hasattr(cfg, "USE_SLOT_SCHEMA_SIMULATOR")


def test_v2_pack_state_shape_remains_rare_reverse1_reverse2_for_sv_and_mega():
    for cfg in [
        ScarletVioletBaseSetConfig,
        MegaEvolutionBaseSetConfig,
        SetPaldeaEvolvedConfig,
        SetPaldeanFatesConfig,
        SetAscendedHeroesConfig,
        SetMegaEvolutionConfig,
    ]:
        model = resolve_pack_state_model(cfg)
        assert set(model.keys()) >= {"state_probabilities", "state_outcomes", "constraints"}
        assert abs(sum(model["state_probabilities"].values()) - 1.0) < 1e-8
        assert model["state_outcomes"]
        for slot_outcomes in model["state_outcomes"].values():
            assert set(slot_outcomes.keys()) == {"rare", "reverse_1", "reverse_2"}


def test_minimal_sv_and_mega_v2_smoke_pack_state_shape_is_stable():
    sv_sample = sample_pack_state(SetPaldeaEvolvedConfig, rng=np.random.default_rng(123))
    mega_sample = sample_pack_state(SetAscendedHeroesConfig, rng=np.random.default_rng(456))

    for sample in [sv_sample, mega_sample]:
        assert sample["entry_path"] == "normal"
        assert isinstance(sample["state"], str)
        assert set(sample["slot_outcomes"].keys()) == {"rare", "reverse_1", "reverse_2"}
