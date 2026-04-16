import pytest

from backend.constants.tcg.pokemon.sharedBaseConfig import BaseSetConfig as SharedRootBaseSetConfig
from backend.constants.tcg.pokemon.megaEvolutionEra.baseConfig import BaseSetConfig as MegaEvolutionBaseSetConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.baseConfig import BaseSetConfig as ScarletVioletBaseSetConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import SetPrismaticEvolutionsConfig
from backend.simulations.monteCarloSimV2 import sample_pack_state
from backend.simulations.utils.packStateModels import eraPackStateBuilders
from backend.simulations.utils.packStateModels import packStateModelOrchestrator as orchestrator_module
from backend.simulations.utils.packStateModels.packStateModelOrchestrator import (
    normalize_era_key,
    resolve_era_builder,
    resolve_pack_state_model,
)
from backend.simulations.utils.packStateModels.scarletAndVioletPackStateModel import (
    build_scarlet_and_violet_pack_state_model,
)


class BaseConfig:
    SLOTS_PER_RARITY = {"common": 4, "uncommon": 3, "reverse": 2, "rare": 1}


def test_shared_root_base_config_is_era_neutral():
    assert SharedRootBaseSetConfig.ERA == ""


def test_normalize_era_key_variants():
    assert normalize_era_key("Scarlet and Violet") == "scarlet_and_violet"
    assert normalize_era_key("Sword & Shield") == "sword_and_shield"
    assert normalize_era_key("Sun-Moon") == "sun_moon"
    assert normalize_era_key("  Black  &  White ") == "black_and_white"
    assert normalize_era_key("Sun---Moon__!!") == "sun_moon"
    assert normalize_era_key("  Scarlet---&---Violet  ") == "scarlet_and_violet"


def test_resolver_prefers_get_pack_state_model():
    class GetterConfig(BaseConfig):
        ERA = "Scarlet and Violet"
        PACK_STATE_MODEL = {
            "state_probabilities": {"baseline": 1.0},
            "state_outcomes": {
                "baseline": {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"}
            },
        }

        @staticmethod
        def get_pack_state_model():
            return {
                "state_probabilities": {"override": 1.0},
                "state_outcomes": {
                    "override": {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"}
                },
            }

    model = resolve_pack_state_model(GetterConfig)
    assert "override" in model["state_probabilities"]
    assert "baseline" not in model["state_probabilities"]


def test_resolver_uses_pack_state_model_when_no_getter():
    class ExplicitModelConfig(BaseConfig):
        ERA = "Scarlet and Violet"
        PACK_STATE_MODEL = {
            "state_probabilities": {"explicit": 1.0},
            "state_outcomes": {
                "explicit": {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"}
            },
        }

    model = resolve_pack_state_model(ExplicitModelConfig)
    assert "explicit" in model["state_probabilities"]


def test_resolver_dynamically_resolves_scarlet_violet_builder():
    class EraConfig(BaseConfig):
        ERA = "Scarlet and Violet"

    model = resolve_pack_state_model(EraConfig)
    assert "baseline" in model["state_probabilities"]
    assert "sir_only" in model["state_probabilities"]


def test_resolver_raises_for_unsupported_named_era():
    class UnknownEraConfig(BaseConfig):
        ERA = "Unregistered Era"

    with pytest.raises(ValueError, match="No pack-state model builder registered"):
        resolve_pack_state_model(UnknownEraConfig)


def test_resolver_allows_fallback_when_era_blank():
    class BlankEraConfig(BaseConfig):
        ERA = "   "

    model = resolve_pack_state_model(BlankEraConfig)
    assert model["state_probabilities"] == {"baseline": 1.0}


def test_resolver_allows_fallback_when_era_missing():
    class MissingEraConfig(BaseConfig):
        pass

    model = resolve_pack_state_model(MissingEraConfig)
    assert model["state_probabilities"] == {"baseline": 1.0}


def test_scarlet_violet_era_base_config_owns_era_identity():
    assert ScarletVioletBaseSetConfig.ERA == "Scarlet and Violet"


def test_mega_evolution_era_base_config_owns_era_identity():
    assert MegaEvolutionBaseSetConfig.ERA == "Mega Evolution"


def test_scarlet_violet_set_configs_inherit_era_from_era_base():
    assert "ERA" not in SetPrismaticEvolutionsConfig.__dict__
    assert SetPrismaticEvolutionsConfig.ERA == "Scarlet and Violet"
    model = resolve_pack_state_model(SetPrismaticEvolutionsConfig)
    assert "baseline" in model["state_probabilities"]


def test_resolver_only_uses_dedicated_builder_namespace(monkeypatch):
    def build_namespace_check_pack_state_model(_config):
        return {
            "state_probabilities": {"should_not_resolve": 1.0},
            "state_outcomes": {
                "should_not_resolve": {
                    "rare": "rare",
                    "reverse_1": "regular reverse",
                    "reverse_2": "regular reverse",
                }
            },
        }

    monkeypatch.setattr(
        orchestrator_module,
        "build_namespace_check_pack_state_model",
        build_namespace_check_pack_state_model,
        raising=False,
    )

    class NamespaceCheckConfig(BaseConfig):
        ERA = "Namespace Check"

    with pytest.raises(ValueError, match="No pack-state model builder registered"):
        resolve_pack_state_model(NamespaceCheckConfig)


def test_dynamic_builder_convention_requires_no_orchestrator_branching(monkeypatch):
    def build_test_new_era_pack_state_model(_config):
        return {
            "state_probabilities": {"new_era": 1.0},
            "state_outcomes": {
                "new_era": {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"}
            },
        }

    monkeypatch.setattr(
        eraPackStateBuilders,
        "build_test_new_era_pack_state_model",
        build_test_new_era_pack_state_model,
        raising=False,
    )

    class NewEraConfig(BaseConfig):
        ERA = "Test New Era"

    model = resolve_pack_state_model(NewEraConfig)
    assert model["state_probabilities"] == {"new_era": 1.0}


def test_resolve_era_builder_returns_none_when_missing():
    assert resolve_era_builder("missing_era") is None


def test_scarlet_violet_builder_outputs_provisional_model_shape():
    model = build_scarlet_and_violet_pack_state_model(BaseConfig)
    assert pytest.approx(1.0, abs=1e-8) == sum(model["state_probabilities"].values())
    assert "state_outcomes" in model
    assert "constraints" in model


def test_simulator_sampling_works_through_orchestrated_resolution():
    class EraConfig(BaseConfig):
        ERA = "Scarlet and Violet"

    sampled = sample_pack_state(EraConfig)
    assert sampled["entry_path"] == "normal"
    assert sampled["state"] in resolve_pack_state_model(EraConfig)["state_probabilities"]
