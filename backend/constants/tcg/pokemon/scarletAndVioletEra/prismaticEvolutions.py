from .baseConfig import BaseSetConfig
from backend.simulations.utils.packStateModels.scarletAndVioletSetOverrides import (
    get_prismatic_evolutions_pack_state_overrides,
)

class SetPrismaticEvolutionsConfig(BaseSetConfig):
    SET_NAME = "Prismatic Evolutions"
    SET_ABBREVIATION = "PRE"
    SET_ID = 'sv8pt5'
    RELEASE_DATE = '2025/01/17'
    PRINTED_TOTAL = 131
    TOTAL = 180
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sv8pt5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sv8pt5/logo.png'

    CARD_DETAILS_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23821/cards/?rows=5000&productTypeID=1" 
    SEALED_DETAILS_URL="https://infinite-api.tcgplayer.com/priceguide/set/23821/cards/?rows=5000&productTypeID=25"
    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/593294/detailed?range=quarter",
        "Mini Tin Price": None,
        "Booster Bundle Price": "https://infinite-api.tcgplayer.com/price/history/600518/detailed?range=quarter",
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/593355/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/610758/detailed?range=quarter" ,
        "Booster Box Price": None,  # Specialty set, does not have one. 
        "Special Collection Price": "https://infinite-api.tcgplayer.com/price/history/622770/detailed?range=quarter"
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Prismatic-Evolutions-Pull-Rates/d94889ea-f76a-4a13-b74d-5b0b071220a7?utm_campaign=18098386707&utm_source=google&utm_medium=cpc&utm_content=&utm_term=&adgroupid=&gad_source=1&gad_campaignid=20946811569&gbraid=0AAAAADHLWY3YDhh7a7GyxYkf06Aq5nXaz&gclid=Cj0KCQjw-4XFBhCBARIsAAdNOktqW8Kws_DAwxJEcS0Pu1nCUAXrjTOiXTA1LY_6HUQjusqjUNBIHkkaAjpOEALw_wcB
        'common' : 46, # 4/46 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 33, # 3/33 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 21,
        'double rare': 106,
        'special illustration rare': 1440,
        'ultra rare': 161,
        'hyper rare': 900,
        # Special cases (checked first)
        'poke ball pattern': 302,
        'master ball pattern': 1362,
        'ace spec rare': 128,
        'god pack': 2000,
        'demi god pack': (1/3) * 2000
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.517547
        "slot_1": {
            "ace spec rare": 1 / 13,
            "poke ball pattern": 1 / 3,
            "regular reverse": 1 - (1 / 13) - (1 / 3) # ≈ 0.589747
        },
        "slot_2": {
            "master ball pattern": 1/20, #TODO: Research
            "special illustration rare": 1 / 45,
            'hyper rare': 1 / 180,
            "regular reverse": 1 - (1 / 20) - (1 / 45) - (1 / 180), # ≈ 0.9278
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 13,
        'rare': 1 - (1 / 6) - (1 / 13),
    }
 
    GOD_PACK_CONFIG = {
        "enabled": True,
        "pull_rate": 1 / 2000,
        "strategy": {
            "type": "fixed",
            "cards": [
                {"name": "Eevee", "number": "074/131", "rarity": "common", "special_type": "master ball"},
                {"name": "Eevee ex", "number": "167/131", "rarity": "special illustration rare"},
                {"name": "Vaporeon ex", "number": "149/131", "rarity": "special illustration rare"},
                {"name": "Jolteon ex", "number": "153/131", "rarity": "special illustration rare"},
                {"name": "Flareon ex", "number": "146/131", "rarity": "special illustration rare"},
                {"name": "Espeon ex", "number": "155/131", "rarity": "special illustration rare"},
                {"name": "Umbreon ex", "number": "161/131", "rarity": "special illustration rare"},
                {"name": "Glaceon ex", "number": "150/131", "rarity": "special illustration rare"},
                {"name": "Leafeon ex", "number": "144/131", "rarity": "special illustration rare"},
                {"name": "Sylveon ex", "number": "156/131", "rarity": "special illustration rare"}
            ]
        }
    }

    DEMI_GOD_PACK_CONFIG = {
        "enabled": True,
        "pull_rate": 3 * (1/2000),
        "strategy": {
            "type": "random",
            "rules": {
                "rarities": {
                    "common": 4,
                    "uncommon": 3,
                    "special illustration rare": 3
                }
            }
        }
    }

    @classmethod
    def get_pack_state_overrides(cls):
        return get_prismatic_evolutions_pack_state_overrides()