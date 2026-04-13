from .bestOfGame import SetBestOfGameConfig
from .legendaryCollection import SetLegendaryCollectionConfig
from .mcdonaldSCollection2011 import SetMcdonaldSCollection2011Config
from .mcdonaldSCollection2012 import SetMcdonaldSCollection2012Config
from .mcdonaldSCollection2014 import SetMcdonaldSCollection2014Config
from .mcdonaldSCollection2015 import SetMcdonaldSCollection2015Config
from .mcdonaldSCollection2016 import SetMcdonaldSCollection2016Config
from .mcdonaldSCollection2017 import SetMcdonaldSCollection2017Config
from .mcdonaldSCollection2018 import SetMcdonaldSCollection2018Config
from .mcdonaldSCollection2019 import SetMcdonaldSCollection2019Config
from .mcdonaldSCollection2021 import SetMcdonaldSCollection2021Config
from .mcdonaldSCollection2022 import SetMcdonaldSCollection2022Config
from .pokMonFutsalCollection import SetPokMonFutsalCollectionConfig
from .pokMonRumble import SetPokMonRumbleConfig
from .southernIslands import SetSouthernIslandsConfig


SET_CONFIG_MAP = {
    'bestOfGame' : SetBestOfGameConfig,
    'legendaryCollection' : SetLegendaryCollectionConfig,
    'mcdonaldSCollection2011' : SetMcdonaldSCollection2011Config,
    'mcdonaldSCollection2012' : SetMcdonaldSCollection2012Config,
    'mcdonaldSCollection2014' : SetMcdonaldSCollection2014Config,
    'mcdonaldSCollection2015' : SetMcdonaldSCollection2015Config,
    'mcdonaldSCollection2016' : SetMcdonaldSCollection2016Config,
    'mcdonaldSCollection2017' : SetMcdonaldSCollection2017Config,
    'mcdonaldSCollection2018' : SetMcdonaldSCollection2018Config,
    'mcdonaldSCollection2019' : SetMcdonaldSCollection2019Config,
    'mcdonaldSCollection2021' : SetMcdonaldSCollection2021Config,
    'mcdonaldSCollection2022' : SetMcdonaldSCollection2022Config,
    'pokMonFutsalCollection' : SetPokMonFutsalCollectionConfig,
    'pokMonRumble' : SetPokMonRumbleConfig,
    'southernIslands' : SetSouthernIslandsConfig,
}

SET_ALIAS_MAP = {
    "base6": "legendaryCollection",
    "best of game": "bestOfGame",
    "bestofgame": "bestOfGame",
    "bp": "bestOfGame",
    "fut20": "pokMonFutsalCollection",
    "lc": "legendaryCollection",
    "legendary collection": "legendaryCollection",
    "legendarycollection": "legendaryCollection",
    "mcd11": "mcdonaldSCollection2011",
    "mcd12": "mcdonaldSCollection2012",
    "mcd14": "mcdonaldSCollection2014",
    "mcd15": "mcdonaldSCollection2015",
    "mcd16": "mcdonaldSCollection2016",
    "mcd17": "mcdonaldSCollection2017",
    "mcd18": "mcdonaldSCollection2018",
    "mcd19": "mcdonaldSCollection2019",
    "mcd21": "mcdonaldSCollection2021",
    "mcd22": "mcdonaldSCollection2022",
    "mcdonald's collection 2011": "mcdonaldSCollection2011",
    "mcdonald's collection 2012": "mcdonaldSCollection2012",
    "mcdonald's collection 2014": "mcdonaldSCollection2014",
    "mcdonald's collection 2015": "mcdonaldSCollection2015",
    "mcdonald's collection 2016": "mcdonaldSCollection2016",
    "mcdonald's collection 2017": "mcdonaldSCollection2017",
    "mcdonald's collection 2018": "mcdonaldSCollection2018",
    "mcdonald's collection 2019": "mcdonaldSCollection2019",
    "mcdonald's collection 2021": "mcdonaldSCollection2021",
    "mcdonald's collection 2022": "mcdonaldSCollection2022",
    "mcdonaldscollection2011": "mcdonaldSCollection2011",
    "mcdonaldscollection2012": "mcdonaldSCollection2012",
    "mcdonaldscollection2014": "mcdonaldSCollection2014",
    "mcdonaldscollection2015": "mcdonaldSCollection2015",
    "mcdonaldscollection2016": "mcdonaldSCollection2016",
    "mcdonaldscollection2017": "mcdonaldSCollection2017",
    "mcdonaldscollection2018": "mcdonaldSCollection2018",
    "mcdonaldscollection2019": "mcdonaldSCollection2019",
    "mcdonaldscollection2021": "mcdonaldSCollection2021",
    "mcdonaldscollection2022": "mcdonaldSCollection2022",
    "pokmonfutsalcollection": "pokMonFutsalCollection",
    "pokmonrumble": "pokMonRumble",
    "pokémon futsal collection": "pokMonFutsalCollection",
    "pokémon rumble": "pokMonRumble",
    "ru1": "pokMonRumble",
    "si1": "southernIslands",
    "southern islands": "southernIslands",
    "southernislands": "southernIslands",
}
