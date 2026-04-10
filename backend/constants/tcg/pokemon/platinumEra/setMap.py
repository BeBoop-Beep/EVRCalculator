from .arceus import SetArceusConfig
from .platinum import SetPlatinumConfig
from .risingRivals import SetRisingRivalsConfig
from .supremeVictors import SetSupremeVictorsConfig


SET_CONFIG_MAP = {
    'arceus' : SetArceusConfig,
    'platinum' : SetPlatinumConfig,
    'risingRivals' : SetRisingRivalsConfig,
    'supremeVictors' : SetSupremeVictorsConfig,
}

SET_ALIAS_MAP = {
    "ar": "arceus",
    "arceus": "arceus",
    "pl": "platinum",
    "pl1": "platinum",
    "pl2": "risingRivals",
    "pl3": "supremeVictors",
    "pl4": "arceus",
    "platinum": "platinum",
    "rising rivals": "risingRivals",
    "risingrivals": "risingRivals",
    "rr": "risingRivals",
    "supreme victors": "supremeVictors",
    "supremevictors": "supremeVictors",
    "sv": "supremeVictors",
}
