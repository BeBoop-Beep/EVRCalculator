from .aquapolis import SetAquapolisConfig
from .expeditionBaseSet import SetExpeditionBaseSetConfig
from .skyridge import SetSkyridgeConfig


SET_CONFIG_MAP = {
    'aquapolis' : SetAquapolisConfig,
    'expeditionBaseSet' : SetExpeditionBaseSetConfig,
    'skyridge' : SetSkyridgeConfig,
}

SET_ALIAS_MAP = {
    "aq": "aquapolis",
    "aquapolis": "aquapolis",
    "ecard1": "expeditionBaseSet",
    "ecard2": "aquapolis",
    "ecard3": "skyridge",
    "ex": "expeditionBaseSet",
    "expedition base set": "expeditionBaseSet",
    "expeditionbaseset": "expeditionBaseSet",
    "sk": "skyridge",
    "skyridge": "skyridge",
}
