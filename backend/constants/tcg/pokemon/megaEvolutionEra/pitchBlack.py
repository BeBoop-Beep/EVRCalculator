from .baseConfig import BaseSetConfig

class SetPitchBlackConfig(BaseSetConfig):
    SET_NAME = 'Pitch Black'
    SET_ABBREVIATION = 'PBL'

    SET_ID = 'me5'
    RELEASE_DATE = '2026/07/17'
    PRINTED_TOTAL = 84
    TOTAL = 120
    SYMBOL_IMAGE_URL = 'https://images.scrydex.com/pokemon/me5-symbol/symbol'
    LOGO_IMAGE_URL = 'https://images.scrydex.com/pokemon/me5-logo/logo'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24688/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24688/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    #
    PULL_RATE_MAPPING = {
        # https://www.facebook.com/HKF3LIX/posts/pfbid02b9vQUSmnXbZECw8YsucAxEWLNJtZWQPRLvNjNi5WGKWkhtfGEm9jdkzqSt5mjj7cl/
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Ascended-Heroes-Pull-Rates/60143d94-88a7-42ce-8e73-babd7b3fabd6/?srsltid=AfmBOoqaUCg2-kUOCbOmVetRPcirK1dhfXgiWRnPtNNWlIxCVAHzitkv
        'common' : 37, # 4/37 (there are 4 commons in each pack with 37 total commons in the set)
        'uncommon': 26, # 3/26 (there are 3 uncommons in each pack with 26 total uncommons in the set)
        'rare': 11,
        'double rare': 48,
        'illustration rare': 100,
        'special illustration rare': 480,
        'ultra rare': 217,
        # Special cases (checked first)
        'mega hyper rare': 1081,
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Approximation model: split published pack-level IR/SIR odds evenly
        # across both reverse slots so the two-slot combined rate stays near
        # intended pull-rate targets within the existing slot-based architecture.
        "slot_1": {
            "regular reverse": 1,
        },
        "slot_2": {
            "illustration rare": 1 / 9, # Same as slot 1 to maintain overall IR pull rate, though actual distribution may differ.
            "special illustration rare": 1 / 80, # 1/80 split of 1/20 IR/SIR combined, which is the published pack-level pull rate for IR+SIR
            "mega hyper rare": 1 / 1081,
            "regular reverse": 1 - (1 / 9) - (1 / 80) - (1 / 1081),
        },
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 5,
        'ultra rare': 1 / 12,
        'rare': 1 - (1 / 5) - (1 / 12), # ≈ 0.483333
    }
 
    GOD_PACK_CONFIG = {
        "enabled": False,
    }

    DEMI_GOD_PACK_CONFIG = {
        "enabled": False,
    }


    @classmethod
    def get_pack_state_overrides(cls):
        from backend.simulations.utils.packStateModels.scarletAndVioletSetOverrides import (
            get_mega_evolution_pack_state_overrides,
        )
        return get_mega_evolution_pack_state_overrides()
