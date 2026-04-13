from .base import SetBaseConfig
from .baseSet2 import SetBaseSet2Config
from .fossil import SetFossilConfig
from .jungle import SetJungleConfig
from .teamRocket import SetTeamRocketConfig
from .wizardsBlackStarPromos import SetWizardsBlackStarPromosConfig


SET_CONFIG_MAP = {
    'base' : SetBaseConfig,
    'baseSet2' : SetBaseSet2Config,
    'fossil' : SetFossilConfig,
    'jungle' : SetJungleConfig,
    'teamRocket' : SetTeamRocketConfig,
    'wizardsBlackStarPromos' : SetWizardsBlackStarPromosConfig,
}

SET_ALIAS_MAP = {
    "b2": "baseSet2",
    "base": "base",
    "base set 2": "baseSet2",
    "base1": "base",
    "base2": "jungle",
    "base3": "fossil",
    "base4": "baseSet2",
    "base5": "teamRocket",
    "basep": "wizardsBlackStarPromos",
    "baseset2": "baseSet2",
    "bs": "base",
    "fo": "fossil",
    "fossil": "fossil",
    "ju": "jungle",
    "jungle": "jungle",
    "pr": "wizardsBlackStarPromos",
    "team rocket": "teamRocket",
    "teamrocket": "teamRocket",
    "tr": "teamRocket",
    "wizards black star promos": "wizardsBlackStarPromos",
    "wizardsblackstarpromos": "wizardsBlackStarPromos",
}
