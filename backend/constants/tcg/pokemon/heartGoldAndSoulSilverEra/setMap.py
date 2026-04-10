from .callOfLegends import SetCallOfLegendsConfig
from .heartgoldAndSoulSilver import SetHeartgoldAndSoulSilverConfig
from .hgssBlackStarPromos import SetHgssBlackStarPromosConfig
from .hsTriumphant import SetHsTriumphantConfig
from .hsUndaunted import SetHsUndauntedConfig
from .hsUnleashed import SetHsUnleashedConfig


SET_CONFIG_MAP = {
    'callOfLegends' : SetCallOfLegendsConfig,
    'heartgoldAndSoulSilver' : SetHeartgoldAndSoulSilverConfig,
    'hgssBlackStarPromos' : SetHgssBlackStarPromosConfig,
    'hsTriumphant' : SetHsTriumphantConfig,
    'hsUndaunted' : SetHsUndauntedConfig,
    'hsUnleashed' : SetHsUnleashedConfig,
}

SET_ALIAS_MAP = {
    "call of legends": "callOfLegends",
    "calloflegends": "callOfLegends",
    "cl": "callOfLegends",
    "col1": "callOfLegends",
    "heartgold & soulsilver": "heartgoldAndSoulSilver",
    "heartgoldandsoulsilver": "heartgoldAndSoulSilver",
    "hgss black star promos": "hgssBlackStarPromos",
    "hgss1": "heartgoldAndSoulSilver",
    "hgss2": "hsUnleashed",
    "hgss3": "hsUndaunted",
    "hgss4": "hsTriumphant",
    "hgssblackstarpromos": "hgssBlackStarPromos",
    "hs": "heartgoldAndSoulSilver",
    "hsp": "hgssBlackStarPromos",
    "hstriumphant": "hsTriumphant",
    "hsundaunted": "hsUndaunted",
    "hsunleashed": "hsUnleashed",
    "hs—triumphant": "hsTriumphant",
    "hs—undaunted": "hsUndaunted",
    "hs—unleashed": "hsUnleashed",
    "pr-hs": "hgssBlackStarPromos",
    "tm": "hsTriumphant",
    "ud": "hsUndaunted",
    "ul": "hsUnleashed",
}
