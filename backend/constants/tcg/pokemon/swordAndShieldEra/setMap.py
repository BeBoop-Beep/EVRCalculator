from .astralRadiance import SetAstralRadianceConfig
from .astralRadianceTrainerGallery import SetAstralRadianceTrainerGalleryConfig
from .battleStyles import SetBattleStylesConfig
from .brilliantStars import SetBrilliantStarsConfig
from .brilliantStarsTrainerGallery import SetBrilliantStarsTrainerGalleryConfig
from .celebrations import SetCelebrationsConfig
from .celebrationsClassicCollection import SetCelebrationsClassicCollectionConfig
from .championSPath import SetChampionSPathConfig
from .chillingReign import SetChillingReignConfig
from .crownZenith import SetCrownZenithConfig
from .crownZenithGalarianGallery import SetCrownZenithGalarianGalleryConfig
from .darknessAblaze import SetDarknessAblazeConfig
from .evolvingSkies import SetEvolvingSkiesConfig
from .fusionStrike import SetFusionStrikeConfig
from .lostOrigin import SetLostOriginConfig
from .lostOriginTrainerGallery import SetLostOriginTrainerGalleryConfig
from .pokMonGO import SetPokMonGOConfig
from .rebelClash import SetRebelClashConfig
from .shiningFates import SetShiningFatesConfig
from .shiningFatesShinyVault import SetShiningFatesShinyVaultConfig
from .silverTempest import SetSilverTempestConfig
from .silverTempestTrainerGallery import SetSilverTempestTrainerGalleryConfig
from .swordAndShield import SetSwordAndShieldConfig
from .swshBlackStarPromos import SetSwshBlackStarPromosConfig
from .vividVoltage import SetVividVoltageConfig


SET_CONFIG_MAP = {
    'astralRadiance' : SetAstralRadianceConfig,
    'astralRadianceTrainerGallery' : SetAstralRadianceTrainerGalleryConfig,
    'battleStyles' : SetBattleStylesConfig,
    'brilliantStars' : SetBrilliantStarsConfig,
    'brilliantStarsTrainerGallery' : SetBrilliantStarsTrainerGalleryConfig,
    'celebrations' : SetCelebrationsConfig,
    'celebrationsClassicCollection' : SetCelebrationsClassicCollectionConfig,
    'championSPath' : SetChampionSPathConfig,
    'chillingReign' : SetChillingReignConfig,
    'crownZenith' : SetCrownZenithConfig,
    'crownZenithGalarianGallery' : SetCrownZenithGalarianGalleryConfig,
    'darknessAblaze' : SetDarknessAblazeConfig,
    'evolvingSkies' : SetEvolvingSkiesConfig,
    'fusionStrike' : SetFusionStrikeConfig,
    'lostOrigin' : SetLostOriginConfig,
    'lostOriginTrainerGallery' : SetLostOriginTrainerGalleryConfig,
    'pokMonGO' : SetPokMonGOConfig,
    'rebelClash' : SetRebelClashConfig,
    'shiningFates' : SetShiningFatesConfig,
    'shiningFatesShinyVault' : SetShiningFatesShinyVaultConfig,
    'silverTempest' : SetSilverTempestConfig,
    'silverTempestTrainerGallery' : SetSilverTempestTrainerGalleryConfig,
    'swordAndShield' : SetSwordAndShieldConfig,
    'swshBlackStarPromos' : SetSwshBlackStarPromosConfig,
    'vividVoltage' : SetVividVoltageConfig,
}

SET_ALIAS_MAP = {
    "asr": "astralRadianceTrainerGallery",
    "astral radiance": "astralRadiance",
    "astral radiance trainer gallery": "astralRadianceTrainerGallery",
    "astralradiance": "astralRadiance",
    "astralradiancetrainergallery": "astralRadianceTrainerGallery",
    "battle styles": "battleStyles",
    "battlestyles": "battleStyles",
    "brilliant stars": "brilliantStars",
    "brilliant stars trainer gallery": "brilliantStarsTrainerGallery",
    "brilliantstars": "brilliantStars",
    "brilliantstarstrainergallery": "brilliantStarsTrainerGallery",
    "brs": "brilliantStarsTrainerGallery",
    "bst": "battleStyles",
    "cel": "celebrationsClassicCollection",
    "cel25": "celebrations",
    "cel25c": "celebrationsClassicCollection",
    "celebrations": "celebrations",
    "celebrations: classic collection": "celebrationsClassicCollection",
    "celebrationsclassiccollection": "celebrationsClassicCollection",
    "champion's path": "championSPath",
    "championspath": "championSPath",
    "chilling reign": "chillingReign",
    "chillingreign": "chillingReign",
    "cpa": "championSPath",
    "cre": "chillingReign",
    "crown zenith": "crownZenith",
    "crown zenith galarian gallery": "crownZenithGalarianGallery",
    "crownzenith": "crownZenith",
    "crownzenithgalariangallery": "crownZenithGalarianGallery",
    "crz": "crownZenithGalarianGallery",
    "daa": "darknessAblaze",
    "darkness ablaze": "darknessAblaze",
    "darknessablaze": "darknessAblaze",
    "evolving skies": "evolvingSkies",
    "evolvingskies": "evolvingSkies",
    "evs": "evolvingSkies",
    "fst": "fusionStrike",
    "fusion strike": "fusionStrike",
    "fusionstrike": "fusionStrike",
    "lor": "lostOriginTrainerGallery",
    "lost origin": "lostOrigin",
    "lost origin trainer gallery": "lostOriginTrainerGallery",
    "lostorigin": "lostOrigin",
    "lostorigintrainergallery": "lostOriginTrainerGallery",
    "pgo": "pokMonGO",
    "pokmongo": "pokMonGO",
    "pokémon go": "pokMonGO",
    "pr-sw": "swshBlackStarPromos",
    "rcl": "rebelClash",
    "rebel clash": "rebelClash",
    "rebelclash": "rebelClash",
    "shf": "shiningFatesShinyVault",
    "shining fates": "shiningFates",
    "shining fates shiny vault": "shiningFatesShinyVault",
    "shiningfates": "shiningFates",
    "shiningfatesshinyvault": "shiningFatesShinyVault",
    "silver tempest": "silverTempest",
    "silver tempest trainer gallery": "silverTempestTrainerGallery",
    "silvertempest": "silverTempest",
    "silvertempesttrainergallery": "silverTempestTrainerGallery",
    "sit": "silverTempestTrainerGallery",
    "ssh": "swordAndShield",
    "sword & shield": "swordAndShield",
    "swordandshield": "swordAndShield",
    "swsh black star promos": "swshBlackStarPromos",
    "swsh1": "swordAndShield",
    "swsh10": "astralRadiance",
    "swsh10tg": "astralRadianceTrainerGallery",
    "swsh11": "lostOrigin",
    "swsh11tg": "lostOriginTrainerGallery",
    "swsh12": "silverTempest",
    "swsh12pt5": "crownZenith",
    "swsh12pt5gg": "crownZenithGalarianGallery",
    "swsh12tg": "silverTempestTrainerGallery",
    "swsh2": "rebelClash",
    "swsh3": "darknessAblaze",
    "swsh35": "championSPath",
    "swsh4": "vividVoltage",
    "swsh45": "shiningFates",
    "swsh45sv": "shiningFatesShinyVault",
    "swsh5": "battleStyles",
    "swsh6": "chillingReign",
    "swsh7": "evolvingSkies",
    "swsh8": "fusionStrike",
    "swsh9": "brilliantStars",
    "swsh9tg": "brilliantStarsTrainerGallery",
    "swshblackstarpromos": "swshBlackStarPromos",
    "swshp": "swshBlackStarPromos",
    "viv": "vividVoltage",
    "vivid voltage": "vividVoltage",
    "vividvoltage": "vividVoltage",
}
