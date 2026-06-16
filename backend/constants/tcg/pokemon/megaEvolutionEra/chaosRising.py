from .baseConfig import BaseSetConfig

class SetChaosRisingConfig(BaseSetConfig):
    SET_NAME = 'Chaos Rising'
    SET_ABBREVIATION = 'CRI'

    SET_ID = 'me4'
    RELEASE_DATE = '2026/05/22'
    PRINTED_TOTAL = 86
    TOTAL = 122
    SYMBOL_IMAGE_URL = 'https://images.scrydex.com/pokemon/me3-symbol/symbol'
    LOGO_IMAGE_URL = 'https://images.scrydex.com/pokemon/me3-logo/logo'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24655/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24655/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Chaos-Rising-Pull-Rates/304e8bfc-175a-4d31-93fe-5bb1be11e5d2/
        # 
        'common' : 38, # 4/38 (there are 4 commons in each pack with 38 total commons in the set)
        'uncommon': 26, # 3/26 (there are 3 uncommons in each pack with 43 total uncommons in the set)
        'rare': 12,
        'double rare': 49,
        'illustration rare': 103,
        'special illustration rare': 496,
        'ultra rare': 217,
        # Special cases (checked first)
        'mega hyper rare': 956,
    }

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1,
        },
        "slot_2": {
            "illustration rare": 1 / 9,
            "special illustration rare": 1 / 83,
            "mega hyper rare": 1 / 956,
            "regular reverse": 1 - (1 / 9) - (1 / 83) - (1 / 956),# ≈ 0.888888
        },
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 5,
        'ultra rare': 1 / 12,
        'rare': 1 - (1 / 5) - (1 / 12), # ≈ 0.482759
    }

    @classmethod
    def get_pack_state_overrides(cls):
        from backend.simulations.utils.packStateModels.scarletAndVioletSetOverrides import get_mega_evolution_pack_state_overrides
        return get_mega_evolution_pack_state_overrides()

