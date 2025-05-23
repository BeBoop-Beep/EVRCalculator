from types import MappingProxyType

class BaseSetConfig:
    RARITY_MAPPING = MappingProxyType({
    # Basic rarities
    'common': 'common',
    'uncommon': 'uncommon',
    'rare': 'rare',
    
    # Rares with special names
    'double rare': 'hits',  # Grouped with standard "rare"
    
    # All "hits" (high-value cards)
    'ultra rare': 'hits',
    'hyper rare': 'hits',
    'illustration rare': 'hits',                # Added this line
    'special illustration rare': 'hits'       
    }) 

class Set151Config(BaseSetConfig):
    SET_NAME = "scarletAndViolet151"
    SCRAPE_PACK_PRICE = "https://infinite-api.tcgplayer.com/price/history/504467/detailed?range=quarter"
    SCRAPE_ETB_PRICE = "https://infinite-api.tcgplayer.com/price/history/503313/detailed?range=quarter"
    SCRAPE_BOOSTER_BOX_PRICE = "" #does not exist
    SCRAPE_SPC_PRICE = "https://infinite-api.tcgplayer.com/price/history/502005/detailed?range=quarter"
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23237/cards/?rows=5000&productTypeID=1" 
    PULL_RATE_MAPPING = {
        'common' : 46, # 4/46 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 33, # 3/33 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 21, # 3/21 (there are 1.21 rares in each pack with 21 total rares in the set)
        'double rare': 90,
        'illustration rare': 188,
        'special illustration rare': 225,
        'ultra rare': 248,
        'hyper rare': 154,
        # Special cases (checked first)
        # 'poke ball pattern': 302,
        # 'master ball pattern': 1362,
        # 'ace spec': 128
    }


class SetPrismaticEvolutionConfig(BaseSetConfig):
    SET_NAME = "prismaticEvolution"
    SCRAPE_CARD_PRICE = ""
    SCRAPE_ETB_PRICE = ""
    SCRAPE_BOOSTER_BOX_PRICE = ""
    SCRAPE_SPC_PRICE = ""
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23821/cards/?rows=5000&productTypeID=1" 
    PULL_RATE_MAPPING = {
        'common' : 46, # 4/46 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 33, # 3/33 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 21, # 3/21 (there are 1.21 rares in each pack with 21 total rares in the set)
        'double rare': 106,
        # 'illustration rare': 188,
        'special illustration rare': 1440,
        'ultra rare': 161,
        'hyper rare': 900,
        # Special cases (checked first)
        'poke ball pattern': 302,
        'master ball pattern': 1362,
        'ace spec': 128
    }


SET_CONFIG_MAP = {
    'scarletAndViolet151' : Set151Config,
    'prismaticEvolution' : SetPrismaticEvolutionConfig,
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
}
