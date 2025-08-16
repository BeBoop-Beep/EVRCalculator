from .destinedRivals import SetDestinedRivalsConfig
from .journeyTogether import SetJourneyTogetherConfig
from .obsidianFlames import SetObsidianFlamesConfig
from .paldeaEvolved import SetPaldeaEvolvedConfig
from .paldeanFates import SetPaldeanFatesConfig
from .paradoxRift import SetParadoxRiftConfig
from .prismaticEvolution import SetPrismaticEvolutionConfig
from .scarletAndViolet151 import Set151Config
from .scarletAndVioletBase import SetScarletAndVioletBaseConfig
from .shroudedFable import SetShroudedFableConfig
from .stellarCrown import SetStellarCrownConfig
from .surgingSparks import SetSurgingSparksConfig
from .temporalForces import SetTemporalForcesConfig
from .twilightMasquerade import SetTwilightMasqueradeConfig
from .whiteFlare import SetWhiteFlareConfig


SET_CONFIG_MAP = {
    'destinedRivals' : SetDestinedRivalsConfig,
    'journeyTogether' : SetJourneyTogetherConfig,
    'obsidianFlames' : SetObsidianFlamesConfig,
    'paldeaEvolved' : SetPaldeaEvolvedConfig,
    'paldeanFates' : SetPaldeanFatesConfig,
    'paradoxRift' : SetParadoxRiftConfig,
    'prismaticEvolution' : SetPrismaticEvolutionConfig,
    'scarletAndViolet151' : Set151Config,
    'scarletAndVioletBase' : SetScarletAndVioletBaseConfig,
    'shroudedFable' : SetShroudedFableConfig,
    'stellarCrown' : SetStellarCrownConfig,
    'surgingSparks' : SetSurgingSparksConfig,
    'temporalForces' : SetTemporalForcesConfig,
    'twilightMasquerade' : SetTwilightMasqueradeConfig,
    'whiteFlare' : SetWhiteFlareConfig,
}

SET_ALIAS_MAP = {
    "151": "scarletAndViolet151",
    "sv151": "scarletAndViolet151",
    "scarlet and violet 151": "scarletAndViolet151",
    "scarlet & violet 151": "scarletAndViolet151",
    "sv 151": "scarletAndViolet151",
    
    "pris": "prismaticEvolution",
    "prismatic": "prismaticEvolution",
    "prismatic evo": "prismaticEvolution",
    "prism evo": "prismaticEvolution",
    "pris evo": "prismaticEvolution",

    "white": "whiteFlare",
    "white flar": "whiteFlare",
    "wf": "whiteFlare",
}
