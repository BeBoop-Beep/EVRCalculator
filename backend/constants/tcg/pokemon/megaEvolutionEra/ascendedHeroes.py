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
        'common' : 84, # 4/84 (there are 4 commons in each pack with 84 total commons is in the set)
        'uncommon': 69, # 3/69 (there are 3 uncommons in each pack with 69 total uncommons in the set)
        'rare': 25,
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
        # Approximation model: split published pack-level IR/SIR odds evenly
        # across both reverse slots so the two-slot combined rate stays near
        # intended pull-rate targets within the existing slot-based architecture.
        "slot_1": {
            "illustration rare": 1 / 18, # 1/9 Published slot-level pull rate for IR, which is the same for both slots in this approximation model. Actual distribution may differ.
            "special illustration rare": 1 / 140, # 1/70 split of 1/20 IR/SIR combined, which is the published pack-level pull rate for IR+SIR
            "regular reverse": 1 - (1 / 18) - (1 / 140),
        },
        "slot_2": {
            "illustration rare": 1 / 18, # Same as slot 1 to maintain overall IR pull rate, though actual distribution may differ.
            "special illustration rare": 1 / 140, # 1/70 split of 1/20 IR/SIR combined, which is the published pack-level pull rate for IR+SIR
            "mega hyper rare": 1 / 540,
            "regular reverse": 1 - (1 / 18) - (1 / 140) - (1 / 540),
        },
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
                "rarities": {
                    "mega attack rare": {"count": 3, "replacement": "without_replacement"},
                    "special illustration rare": {"count": 7, "replacement": "without_replacement"},
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
