from .baseConfig import BaseSetConfig
from backend.simulations.utils.packStateModels.scarletAndVioletSetOverrides import (
    get_mega_evolution_pack_state_overrides,
)

class SetMegaEvolutionConfig(BaseSetConfig):
    SET_NAME = 'Mega Evolution'
    SET_ABBREVIATION = 'MEG'

    SET_ID = 'me1'
    RELEASE_DATE = '2025/09/26'
    PRINTED_TOTAL = 132
    TOTAL = 188
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/me1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/me1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24380/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24380/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Mega-Evolution-Pull-Rates/40cbeedc-21ce-473b-aef1-74e3969d9f91/?utm_campaign=21021596617&utm_source=google&utm_medium=cpc&utm_content=&utm_term=&adgroupid=&gad_source=1&gad_campaignid=21018486656&gbraid=0AAAAADHLWY2yXvlMZcx7Cw6cKcenkmnST&gclid=CjwKCAjw46HPBhAMEiwASZpLRLmndOD5zb7kFGaHlFhUg47jBqHq_9O7Tux7diE_csSKs4kkbohirhoCe9AQAvD_BwE
        'common' : 67, # 4/67 (there are 4 commons in each pack with 67 total commons is in the set)
        'uncommon': 43, # 3/43 (there are 3 uncommons in each pack with 43 total uncommons in the set)
        'rare': 12,
        'double rare': 48,
        'illustration rare': 202,
        'special illustration rare': 1008,
        'ultra rare': 267,
        # Special cases (checked first)
        'mega hyper rare': 2520,
    }

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1,
        },
        "slot_2": {
            "illustration rare": 1 / 9, 
            "special illustration rare": 1 / 101,
            "mega hyper rare": 1 / 1260,
            "regular reverse": 1 - (1 / 9) - (1 / 101) - (1 / 1260),# ≈ 0.888888
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
