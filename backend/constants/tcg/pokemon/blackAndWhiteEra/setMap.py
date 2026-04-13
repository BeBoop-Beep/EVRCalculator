from .blackAndWhite import SetBlackAndWhiteConfig
from .boundariesCrossed import SetBoundariesCrossedConfig
from .bwBlackStarPromos import SetBwBlackStarPromosConfig
from .darkExplorers import SetDarkExplorersConfig
from .dragonsExalted import SetDragonsExaltedConfig
from .dragonVault import SetDragonVaultConfig
from .emergingPowers import SetEmergingPowersConfig
from .legendaryTreasures import SetLegendaryTreasuresConfig
from .nextDestinies import SetNextDestiniesConfig
from .nobleVictories import SetNobleVictoriesConfig
from .plasmaBlast import SetPlasmaBlastConfig
from .plasmaFreeze import SetPlasmaFreezeConfig
from .plasmaStorm import SetPlasmaStormConfig


SET_CONFIG_MAP = {
    'blackAndWhite' : SetBlackAndWhiteConfig,
    'boundariesCrossed' : SetBoundariesCrossedConfig,
    'bwBlackStarPromos' : SetBwBlackStarPromosConfig,
    'darkExplorers' : SetDarkExplorersConfig,
    'dragonsExalted' : SetDragonsExaltedConfig,
    'dragonVault' : SetDragonVaultConfig,
    'emergingPowers' : SetEmergingPowersConfig,
    'legendaryTreasures' : SetLegendaryTreasuresConfig,
    'nextDestinies' : SetNextDestiniesConfig,
    'nobleVictories' : SetNobleVictoriesConfig,
    'plasmaBlast' : SetPlasmaBlastConfig,
    'plasmaFreeze' : SetPlasmaFreezeConfig,
    'plasmaStorm' : SetPlasmaStormConfig,
}

SET_ALIAS_MAP = {
    "bcr": "boundariesCrossed",
    "black & white": "blackAndWhite",
    "blackandwhite": "blackAndWhite",
    "blw": "blackAndWhite",
    "boundaries crossed": "boundariesCrossed",
    "boundariescrossed": "boundariesCrossed",
    "bw black star promos": "bwBlackStarPromos",
    "bw1": "blackAndWhite",
    "bw10": "plasmaBlast",
    "bw11": "legendaryTreasures",
    "bw2": "emergingPowers",
    "bw3": "nobleVictories",
    "bw4": "nextDestinies",
    "bw5": "darkExplorers",
    "bw6": "dragonsExalted",
    "bw7": "boundariesCrossed",
    "bw8": "plasmaStorm",
    "bw9": "plasmaFreeze",
    "bwblackstarpromos": "bwBlackStarPromos",
    "bwp": "bwBlackStarPromos",
    "dark explorers": "darkExplorers",
    "darkexplorers": "darkExplorers",
    "dex": "darkExplorers",
    "dragon vault": "dragonVault",
    "dragons exalted": "dragonsExalted",
    "dragonsexalted": "dragonsExalted",
    "dragonvault": "dragonVault",
    "drv": "dragonVault",
    "drx": "dragonsExalted",
    "dv1": "dragonVault",
    "emerging powers": "emergingPowers",
    "emergingpowers": "emergingPowers",
    "epo": "emergingPowers",
    "legendary treasures": "legendaryTreasures",
    "legendarytreasures": "legendaryTreasures",
    "ltr": "legendaryTreasures",
    "next destinies": "nextDestinies",
    "nextdestinies": "nextDestinies",
    "noble victories": "nobleVictories",
    "noblevictories": "nobleVictories",
    "nvi": "nobleVictories",
    "nxd": "nextDestinies",
    "plasma blast": "plasmaBlast",
    "plasma freeze": "plasmaFreeze",
    "plasma storm": "plasmaStorm",
    "plasmablast": "plasmaBlast",
    "plasmafreeze": "plasmaFreeze",
    "plasmastorm": "plasmaStorm",
    "plb": "plasmaBlast",
    "plf": "plasmaFreeze",
    "pls": "plasmaStorm",
    "pr-blw": "bwBlackStarPromos",
}
