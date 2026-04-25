from backend.simulations.utils.packStateModels.scarletAndVioletSetOverrides import get_mega_evolution_pack_state_overrides

from .baseConfig import BaseSetConfig

class SetPerfectOrderConfig(BaseSetConfig):
    SET_NAME = 'Perfect Order'
    SET_ABBREVIATION = 'POR'

    SET_ID = 'me3'
    RELEASE_DATE = '2026/03/27'
    PRINTED_TOTAL = 88
    TOTAL = 124
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/me3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/me3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24587/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24587/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Perfect-Order-Pull-Rates/73148119-ebcb-40b7-84b6-52b3a6d0c631/?utm_campaign=23396674211&utm_source=google&utm_medium=cpc&utm_content=&utm_term=&adgroupid=&gad_source=1&gad_campaignid=23396680751&gbraid=0AAAAADHLWY3kpCYLth86avOCRrRsvfDeD&gclid=CjwKCAjw46HPBhAMEiwASZpLRHHIWnpn-Jf6eRmOc0n4DLP4a0WpbsvhozSg6rvUVPYl6p-3uDL_QhoCsiQQAvD_BwE
        # 
        'common' : 67, # 4/67 (there are 4 commons in each pack with 67 total commons is in the set)
        'uncommon': 43, # 3/43 (there are 3 uncommons in each pack with 43 total uncommons in the set)
        'rare': 12,
        'double rare': 43,
        'illustration rare': 98,
        'special illustration rare': 487,
        'ultra rare': 211,
        # Special cases (checked first)
        'mega hyper rare': 1786,
    }

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1,
        },
        "slot_2": {
            "illustration rare": 1 / 9,
            "special illustration rare": 1 / 81,
            "mega hyper rare": 1 / 1786,
            "regular reverse": 1 - (1 / 9) - (1 / 81) - (1 / 1786),# ≈ 0.888888
        },
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 5,
        'ultra rare': 1 / 12,
        'rare': 1 - (1 / 5) - (1 / 12), # ≈ 0.482759
    }

    @classmethod
    def get_pack_state_overrides(cls):
        return get_mega_evolution_pack_state_overrides()

