from .ancientOrigins import SetAncientOriginsConfig
from .breakpoint import SetBreakpointConfig
from .breakthrough import SetBreakthroughConfig
from .doubleCrisis import SetDoubleCrisisConfig
from .evolutions import SetEvolutionsConfig
from .fatesCollide import SetFatesCollideConfig
from .flashfire import SetFlashfireConfig
from .furiousFists import SetFuriousFistsConfig
from .generations import SetGenerationsConfig
from .kalosStarterSet import SetKalosStarterSetConfig
from .phantomForces import SetPhantomForcesConfig
from .primalClash import SetPrimalClashConfig
from .roaringSkies import SetRoaringSkiesConfig
from .steamSiege import SetSteamSiegeConfig
from .xy import SetXyConfig
from .xyBlackStarPromos import SetXyBlackStarPromosConfig


SET_CONFIG_MAP = {
    'ancientOrigins' : SetAncientOriginsConfig,
    'breakpoint' : SetBreakpointConfig,
    'breakthrough' : SetBreakthroughConfig,
    'doubleCrisis' : SetDoubleCrisisConfig,
    'evolutions' : SetEvolutionsConfig,
    'fatesCollide' : SetFatesCollideConfig,
    'flashfire' : SetFlashfireConfig,
    'furiousFists' : SetFuriousFistsConfig,
    'generations' : SetGenerationsConfig,
    'kalosStarterSet' : SetKalosStarterSetConfig,
    'phantomForces' : SetPhantomForcesConfig,
    'primalClash' : SetPrimalClashConfig,
    'roaringSkies' : SetRoaringSkiesConfig,
    'steamSiege' : SetSteamSiegeConfig,
    'xy' : SetXyConfig,
    'xyBlackStarPromos' : SetXyBlackStarPromosConfig,
}

SET_ALIAS_MAP = {
    "ancient origins": "ancientOrigins",
    "ancientorigins": "ancientOrigins",
    "aor": "ancientOrigins",
    "bkp": "breakpoint",
    "bkt": "breakthrough",
    "breakpoint": "breakpoint",
    "breakthrough": "breakthrough",
    "dc1": "doubleCrisis",
    "dcr": "doubleCrisis",
    "double crisis": "doubleCrisis",
    "doublecrisis": "doubleCrisis",
    "evo": "evolutions",
    "evolutions": "evolutions",
    "fates collide": "fatesCollide",
    "fatescollide": "fatesCollide",
    "fco": "fatesCollide",
    "ffi": "furiousFists",
    "flashfire": "flashfire",
    "flf": "flashfire",
    "furious fists": "furiousFists",
    "furiousfists": "furiousFists",
    "g1": "generations",
    "gen": "generations",
    "generations": "generations",
    "kalos starter set": "kalosStarterSet",
    "kalosstarterset": "kalosStarterSet",
    "kss": "kalosStarterSet",
    "phantom forces": "phantomForces",
    "phantomforces": "phantomForces",
    "phf": "phantomForces",
    "pr-xy": "xyBlackStarPromos",
    "prc": "primalClash",
    "primal clash": "primalClash",
    "primalclash": "primalClash",
    "roaring skies": "roaringSkies",
    "roaringskies": "roaringSkies",
    "ros": "roaringSkies",
    "steam siege": "steamSiege",
    "steamsiege": "steamSiege",
    "sts": "steamSiege",
    "xy": "xy",
    "xy black star promos": "xyBlackStarPromos",
    "xy0": "kalosStarterSet",
    "xy1": "xy",
    "xy10": "fatesCollide",
    "xy11": "steamSiege",
    "xy12": "evolutions",
    "xy2": "flashfire",
    "xy3": "furiousFists",
    "xy4": "phantomForces",
    "xy5": "primalClash",
    "xy6": "roaringSkies",
    "xy7": "ancientOrigins",
    "xy8": "breakthrough",
    "xy9": "breakpoint",
    "xyblackstarpromos": "xyBlackStarPromos",
    "xyp": "xyBlackStarPromos",
}
