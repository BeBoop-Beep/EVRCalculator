from .baseConfig import BaseSetConfig
from backend.simulations.utils.packStateModels.scarletAndVioletSetOverrides import (
    get_ascended_heroes_pack_state_overrides,
)

class SetAscendedHeroesConfig(BaseSetConfig):
    SET_NAME = 'Ascended Heroes'
    SET_ABBREVIATION = 'ASC'

    SET_ID = 'me2pt5'
    RELEASE_DATE = '2026/01/30'
    PRINTED_TOTAL = 217
    TOTAL = 295
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/me2pt5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/me2pt5/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24541/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24541/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    #
    PULL_RATE_MAPPING = {
        # https://www.facebook.com/HKF3LIX/posts/pfbid02b9vQUSmnXbZECw8YsucAxEWLNJtZWQPRLvNjNi5WGKWkhtfGEm9jdkzqSt5mjj7cl/
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Ascended-Heroes-Pull-Rates/60143d94-88a7-42ce-8e73-babd7b3fabd6/?srsltid=AfmBOoqaUCg2-kUOCbOmVetRPcirK1dhfXgiWRnPtNNWlIxCVAHzitkv
        'common' : 38, # 4/38 (there are 4 commons in each pack with 38 total commons is in the set)
        'uncommon': 32, # 3/32 (there are 3 uncommons in each pack with 32 total uncommons in the set)
        'rare': 10,
        'double rare': 191,
        'illustration rare': 293,
        'special illustration rare': 1533,
        'ultra rare': 291,
        # Special cases (checked first)
        'mega attack rare' : 202,
        'mega hyper rare': 1080,
        'god pack': 2000,
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.517547
        "slot_1": {
            'illustration rare': 1/9,
            "special illustration rare": 1/70,
            "regular reverse": 1 - (1/9) - (1/70) # ≈ 0.818518
        },
        "slot_2": {
            'illustration rare': 1/9,
            "special illustration rare": 1/70,
            "mega hyper rare": 1/540,
            "regular reverse": 1 - (1/9) - (1 / 70) - (1/540)  # ≈ 0.816667
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 5,
        'ultra rare': 1 / 21,
        'mega attack rare': 1 / 29,
        'rare': 1 - (1 / 5) - (1 / 21) - (1 / 29), # ≈ 0.482759
    }
 
    GOD_PACK_CONFIG = {
        "enabled": True,
        "pull_rate": 1 / 2000,
        "strategy": {
            "type": "random",  # or "fixed"
            "rules": {
                # Option A: unified pool
                # "count": 11,
                # "rarities": ["Illustration Rare", "Special Illustration Rare"]

                # Option B: split by slot
                "rarities": {
                    "mega attack rare": 3,
                    "special illustration rare": 7,
                }
            }
        }
    }

    DEMI_GOD_PACK_CONFIG = {
        "enabled": False,
    }


    @classmethod
    def get_pack_state_overrides(cls):
        return get_ascended_heroes_pack_state_overrides()
