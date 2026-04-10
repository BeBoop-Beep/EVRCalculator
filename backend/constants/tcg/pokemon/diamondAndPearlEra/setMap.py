from .diamondAndPearl import SetDiamondAndPearlConfig
from .dpBlackStarPromos import SetDpBlackStarPromosConfig
from .greatEncounters import SetGreatEncountersConfig
from .legendsAwakened import SetLegendsAwakenedConfig
from .majesticDawn import SetMajesticDawnConfig
from .mysteriousTreasures import SetMysteriousTreasuresConfig
from .secretWonders import SetSecretWondersConfig
from .stormfront import SetStormfrontConfig


SET_CONFIG_MAP = {
    'diamondAndPearl' : SetDiamondAndPearlConfig,
    'dpBlackStarPromos' : SetDpBlackStarPromosConfig,
    'greatEncounters' : SetGreatEncountersConfig,
    'legendsAwakened' : SetLegendsAwakenedConfig,
    'majesticDawn' : SetMajesticDawnConfig,
    'mysteriousTreasures' : SetMysteriousTreasuresConfig,
    'secretWonders' : SetSecretWondersConfig,
    'stormfront' : SetStormfrontConfig,
}

SET_ALIAS_MAP = {
    "diamond & pearl": "diamondAndPearl",
    "diamondandpearl": "diamondAndPearl",
    "dp": "diamondAndPearl",
    "dp black star promos": "dpBlackStarPromos",
    "dp1": "diamondAndPearl",
    "dp2": "mysteriousTreasures",
    "dp3": "secretWonders",
    "dp4": "greatEncounters",
    "dp5": "majesticDawn",
    "dp6": "legendsAwakened",
    "dp7": "stormfront",
    "dpblackstarpromos": "dpBlackStarPromos",
    "dpp": "dpBlackStarPromos",
    "ge": "greatEncounters",
    "great encounters": "greatEncounters",
    "greatencounters": "greatEncounters",
    "la": "legendsAwakened",
    "legends awakened": "legendsAwakened",
    "legendsawakened": "legendsAwakened",
    "majestic dawn": "majesticDawn",
    "majesticdawn": "majesticDawn",
    "md": "majesticDawn",
    "mt": "mysteriousTreasures",
    "mysterious treasures": "mysteriousTreasures",
    "mysterioustreasures": "mysteriousTreasures",
    "pr-dpp": "dpBlackStarPromos",
    "secret wonders": "secretWonders",
    "secretwonders": "secretWonders",
    "sf": "stormfront",
    "stormfront": "stormfront",
    "sw": "secretWonders",
}
