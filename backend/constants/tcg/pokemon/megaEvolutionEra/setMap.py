from backend.constants.tcg.pokemon.megaEvolutionEra.chaosRising import SetChaosRisingConfig

from .ascendedHeroes import SetAscendedHeroesConfig
from .megaEvolution import SetMegaEvolutionConfig
from .perfectOrder import SetPerfectOrderConfig
from .phantasmalFlames import SetPhantasmalFlamesConfig


SET_CONFIG_MAP = {
    'ascendedHeroes' : SetAscendedHeroesConfig,
    'megaEvolution' : SetMegaEvolutionConfig,
    'perfectOrder' : SetPerfectOrderConfig,
    'phantasmalFlames' : SetPhantasmalFlamesConfig,
    'chaosRising' : SetChaosRisingConfig,
}

SET_ALIAS_MAP = {
    "asc": "ascendedHeroes",
    "ascended heroes": "ascendedHeroes",
    "ascendedheroes": "ascendedHeroes",
    "chaos rising": "chaosRising",
    "chaosrising": "chaosRising",
    "cri": "chaosRising",
    "me1": "megaEvolution",
    "me2": "phantasmalFlames",
    "me2pt5": "ascendedHeroes",
    "me3": "perfectOrder",
    "me4": "chaosRising",
    "meg": "megaEvolution",
    "mega evolution": "megaEvolution",
    "megaevolution": "megaEvolution",
    "perfect order": "perfectOrder",
    "perfectorder": "perfectOrder",
    "pfl": "phantasmalFlames",
    "phantasmal flames": "phantasmalFlames",
    "phantasmalflames": "phantasmalFlames",
    "por": "perfectOrder",
}
