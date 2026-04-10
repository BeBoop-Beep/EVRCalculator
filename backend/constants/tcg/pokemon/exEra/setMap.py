from .crystalGuardians import SetCrystalGuardiansConfig
from .deltaSpecies import SetDeltaSpeciesConfig
from .deoxys import SetDeoxysConfig
from .dragon import SetDragonConfig
from .dragonFrontiers import SetDragonFrontiersConfig
from .emerald import SetEmeraldConfig
from .exTrainerKit2Minun import SetExTrainerKit2MinunConfig
from .exTrainerKit2Plusle import SetExTrainerKit2PlusleConfig
from .exTrainerKitLatias import SetExTrainerKitLatiasConfig
from .exTrainerKitLatios import SetExTrainerKitLatiosConfig
from .fireredAndLeafGreen import SetFireredAndLeafGreenConfig
from .hiddenLegends import SetHiddenLegendsConfig
from .holonPhantoms import SetHolonPhantomsConfig
from .legendMaker import SetLegendMakerConfig
from .powerKeepers import SetPowerKeepersConfig
from .rubyAndSapphire import SetRubyAndSapphireConfig
from .sandstorm import SetSandstormConfig
from .teamMagmaVsTeamAqua import SetTeamMagmaVsTeamAquaConfig
from .teamRocketReturns import SetTeamRocketReturnsConfig
from .unseenForces import SetUnseenForcesConfig


SET_CONFIG_MAP = {
    'crystalGuardians' : SetCrystalGuardiansConfig,
    'deltaSpecies' : SetDeltaSpeciesConfig,
    'deoxys' : SetDeoxysConfig,
    'dragon' : SetDragonConfig,
    'dragonFrontiers' : SetDragonFrontiersConfig,
    'emerald' : SetEmeraldConfig,
    'exTrainerKit2Minun' : SetExTrainerKit2MinunConfig,
    'exTrainerKit2Plusle' : SetExTrainerKit2PlusleConfig,
    'exTrainerKitLatias' : SetExTrainerKitLatiasConfig,
    'exTrainerKitLatios' : SetExTrainerKitLatiosConfig,
    'fireredAndLeafGreen' : SetFireredAndLeafGreenConfig,
    'hiddenLegends' : SetHiddenLegendsConfig,
    'holonPhantoms' : SetHolonPhantomsConfig,
    'legendMaker' : SetLegendMakerConfig,
    'powerKeepers' : SetPowerKeepersConfig,
    'rubyAndSapphire' : SetRubyAndSapphireConfig,
    'sandstorm' : SetSandstormConfig,
    'teamMagmaVsTeamAqua' : SetTeamMagmaVsTeamAquaConfig,
    'teamRocketReturns' : SetTeamRocketReturnsConfig,
    'unseenForces' : SetUnseenForcesConfig,
}

SET_ALIAS_MAP = {
    "cg": "crystalGuardians",
    "crystal guardians": "crystalGuardians",
    "crystalguardians": "crystalGuardians",
    "delta species": "deltaSpecies",
    "deltaspecies": "deltaSpecies",
    "deoxys": "deoxys",
    "df": "dragonFrontiers",
    "dr": "dragon",
    "dragon": "dragon",
    "dragon frontiers": "dragonFrontiers",
    "dragonfrontiers": "dragonFrontiers",
    "ds": "deltaSpecies",
    "dx": "deoxys",
    "em": "emerald",
    "emerald": "emerald",
    "ex trainer kit 2 minun": "exTrainerKit2Minun",
    "ex trainer kit 2 plusle": "exTrainerKit2Plusle",
    "ex trainer kit latias": "exTrainerKitLatias",
    "ex trainer kit latios": "exTrainerKitLatios",
    "ex1": "rubyAndSapphire",
    "ex10": "unseenForces",
    "ex11": "deltaSpecies",
    "ex12": "legendMaker",
    "ex13": "holonPhantoms",
    "ex14": "crystalGuardians",
    "ex15": "dragonFrontiers",
    "ex16": "powerKeepers",
    "ex2": "sandstorm",
    "ex3": "dragon",
    "ex4": "teamMagmaVsTeamAqua",
    "ex5": "hiddenLegends",
    "ex6": "fireredAndLeafGreen",
    "ex7": "teamRocketReturns",
    "ex8": "deoxys",
    "ex9": "emerald",
    "extrainerkit2minun": "exTrainerKit2Minun",
    "extrainerkit2plusle": "exTrainerKit2Plusle",
    "extrainerkitlatias": "exTrainerKitLatias",
    "extrainerkitlatios": "exTrainerKitLatios",
    "firered & leafgreen": "fireredAndLeafGreen",
    "fireredandleafgreen": "fireredAndLeafGreen",
    "hidden legends": "hiddenLegends",
    "hiddenlegends": "hiddenLegends",
    "hl": "hiddenLegends",
    "holon phantoms": "holonPhantoms",
    "holonphantoms": "holonPhantoms",
    "hp": "holonPhantoms",
    "legend maker": "legendMaker",
    "legendmaker": "legendMaker",
    "lm": "legendMaker",
    "ma": "teamMagmaVsTeamAqua",
    "pk": "powerKeepers",
    "power keepers": "powerKeepers",
    "powerkeepers": "powerKeepers",
    "rg": "fireredAndLeafGreen",
    "rs": "rubyAndSapphire",
    "ruby & sapphire": "rubyAndSapphire",
    "rubyandsapphire": "rubyAndSapphire",
    "sandstorm": "sandstorm",
    "ss": "sandstorm",
    "team magma vs team aqua": "teamMagmaVsTeamAqua",
    "team rocket returns": "teamRocketReturns",
    "teammagmavsteamaqua": "teamMagmaVsTeamAqua",
    "teamrocketreturns": "teamRocketReturns",
    "tk1a": "exTrainerKitLatias",
    "tk1b": "exTrainerKitLatios",
    "tk2a": "exTrainerKit2Plusle",
    "tk2b": "exTrainerKit2Minun",
    "trr": "teamRocketReturns",
    "uf": "unseenForces",
    "unseen forces": "unseenForces",
    "unseenforces": "unseenForces",
}
