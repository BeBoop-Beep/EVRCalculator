from types import MappingProxyType

class BaseSetConfig:
    RARITY_MAPPING = MappingProxyType({
    # Basic rarities
    'common': 'common',
    'uncommon': 'uncommon',
    'rare': 'rare',
    
    # All "hits" (high-value cards)
    'double rare': 'hits', 
    'ace spec rare': 'hits',
    'poke ball pattern': 'hits',
    'master ball pattern': 'hits',
    'ultra rare': 'hits',
    'hyper rare': 'hits',
    'illustration rare': 'hits',             
    'special illustration rare': 'hits'       
    }) 

    @classmethod
    def get_rarity_pack_multiplier(cls):
        """Dynamically calculate pack multipliers from pull rate mapping."""
        base_multipliers = {}

        if 'common' in cls.PULL_RATE_MAPPING:
            base_multipliers['common'] = 4
        if 'uncommon' in cls.PULL_RATE_MAPPING:
            base_multipliers['uncommon'] = 3

        return {
            **base_multipliers,
            **{
                rarity: 1 / cls.PULL_RATE_MAPPING[rarity]
                for rarity in cls.PULL_RATE_MAPPING
                if rarity not in ['common', 'uncommon']
            }
        }

class Set151Config(BaseSetConfig):
    SET_NAME = "scarletAndViolet151"
    SCRAPE_PACK_PRICE = "https://infinite-api.tcgplayer.com/price/history/504467/detailed?range=quarter"
    SCRAPE_ETB_PRICE = "https://infinite-api.tcgplayer.com/price/history/503313/detailed?range=quarter"
    SCRAPE_BOOSTER_BOX_PRICE = ""  # No booster box
    SCRAPE_SPC_PRICE = "https://infinite-api.tcgplayer.com/price/history/502005/detailed?range=quarter"
    SCRAPE_URL = "https://infinite-api.tcgplayer.com/priceguide/set/23237/cards/?rows=5000&productTypeID=1"

    PULL_RATE_MAPPING = {
        'common': 46,
        'uncommon': 33,
        'rare': 21,
        'double rare': 90,
        'illustration rare': 188,
        'special illustration rare': 225,
        'ultra rare': 248,
        'hyper rare': 154,
    }

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular_reverse": 1
        },
        "slot_2": {
            "illustration_rare": 1/12,
            "special_illustration_rare": 1 / 32,
            "regular_reverse": 1 - (1 / 12) - (1 / 32)  # ≈ 0.9278
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 8,
        'ultra rare': 1 / 16,
        'hyper rare': 1 / 51,
        'rare': 1 - (1 / 8) - (1 / 16) - (1 / 51),
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

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "ace_spec": 1/13,
            "pokeball_pattern": 1/3,
            "regular_reverse": 1 - (1/13) - (1/3)
        },
        "slot_2": {
            "masterball_pattern": 1/20,
            "special_illustration_rare": 1 / 45,
            "regular_reverse": 1 - (1 / 20) - (1 / 45)  # ≈ 0.9278
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 13,
        'hyper rare': 1 / 180,
        'rare': 1 - (1 / 6) - (1 / 13) - (1 / 180),
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
