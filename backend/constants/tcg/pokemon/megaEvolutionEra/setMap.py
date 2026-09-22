from backend.constants.tcg.pokemon.megaEvolutionEra.chaosRising import SetChaosRisingConfig

from .ascendedHeroes import SetAscendedHeroesConfig
from .megaEvolution import SetMegaEvolutionConfig
from .perfectOrder import SetPerfectOrderConfig
from .phantasmalFlames import SetPhantasmalFlamesConfig
from .pitchBlack import SetPitchBlackConfig
from .megaEvolutionPromos import SetMegaEvolutionPromosConfig
from .me06DeltaReign import SetMe06DeltaReignConfig
from .me30thCelebrationClassicCollection import SetMe30thCelebrationClassicCollectionConfig


SET_CONFIG_MAP = {
    'ascendedHeroes' : SetAscendedHeroesConfig,
    'megaEvolution' : SetMegaEvolutionConfig,
    'perfectOrder' : SetPerfectOrderConfig,
    'phantasmalFlames' : SetPhantasmalFlamesConfig,
    'chaosRising' : SetChaosRisingConfig,
    'pitchBlack' : SetPitchBlackConfig,
    'megaEvolutionPromos': SetMegaEvolutionPromosConfig,
    'me06DeltaReign': SetMe06DeltaReignConfig,
    'me30thCelebrationClassicCollection': SetMe30thCelebrationClassicCollectionConfig,
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
    "mep": "megaEvolutionPromos",
    "mega evolution promo": "megaEvolutionPromos",
    "mega evolution": "megaEvolution",
    "megaevolution": "megaEvolution",
    "pbl": "pitchBlack",
    "pitch black": "pitchBlack",
    "pitchblack": "pitchBlack",
    "perfect order": "perfectOrder",
    "perfectorder": "perfectOrder",
    "pfl": "phantasmalFlames",
    "phantasmal flames": "phantasmalFlames",
    "phantasmalflames": "phantasmalFlames",
    "por": "perfectOrder",
    "24831": "me06DeltaReign",
    "delta reign": "me06DeltaReign",
    "me06 delta reign": "me06DeltaReign",
    "me06deltareign": "me06DeltaReign",
    "24837": "me30thCelebrationClassicCollection",
    "me55c": "me30thCelebrationClassicCollection",
    "30th celebration classic collection": "me30thCelebrationClassicCollection",
    "30th celebration: classic collection": "me30thCelebrationClassicCollection",
    "me 30th celebration classic collection": "me30thCelebrationClassicCollection",
    "me30thcelebrationclassiccollection": "me30thCelebrationClassicCollection",
}
