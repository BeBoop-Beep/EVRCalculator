from backend.constants.tcg.pokemon.megaEvolutionEra.ascendedHeroes import SetAscendedHeroesConfig
from backend.jobs.evr_runner import _resolve_set_config


def test_resolve_set_config_ascended_heroes_name_alias():
    config_cls, canonical_key = _resolve_set_config("ascended heroes")
    assert config_cls is SetAscendedHeroesConfig
    assert canonical_key == "ascendedHeroes"


def test_resolve_set_config_asc_short_alias():
    config_cls, canonical_key = _resolve_set_config("asc")
    assert config_cls is SetAscendedHeroesConfig
    assert canonical_key == "ascendedHeroes"


def test_resolve_set_config_me2pt5_alias():
    config_cls, canonical_key = _resolve_set_config("me2pt5")
    assert config_cls is SetAscendedHeroesConfig
    assert canonical_key == "ascendedHeroes"
