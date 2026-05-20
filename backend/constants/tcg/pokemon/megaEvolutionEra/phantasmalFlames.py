from .baseConfig import BaseSetConfig

class SetPhantasmalFlamesConfig(BaseSetConfig):
    SET_NAME = 'Phantasmal Flames'
    SET_ABBREVIATION = 'PFL'

    SET_ID = 'me2'
    RELEASE_DATE = '2025/11/14'
    PRINTED_TOTAL = 94
    TOTAL = 130
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/me2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/me2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24448/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24448/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    PULL_RATE_MAPPING = {
        # https://www.binderforge.com/phantasmal-flames-master-set/
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Phantasmal-Flames-Pull-Rates/9abae60d-b7fb-448f-874e-176f78d6a6ca/?utm_campaign=18147618381&utm_source=google&utm_medium=cpc&utm_content=&utm_term=&adgroupid=&gad_source=1&gad_campaignid=20946812631&gbraid=0AAAAADHLWY0SvnW0hw-zyPBuY5XBbJtOq&gclid=CjwKCAjw46HPBhAMEiwASZpLRAdCTLRWfmtTQPyAm8JTGr7mHrDRKtfwpYkSPF0hKt2eM-J6RXft7hoCQsAQAvD_BwE
        'common' : 43, # 4/43 (there are 4 commons in each pack with 84 total commons is in the set)
        'uncommon': 31, # 3/31 (there are 3 uncommons in each pack with 31 total uncommons in the set)
        'rare': 8,
        'double rare': 48,
        'illustration rare': 118,
        'special illustration rare': 400,
        'ultra rare': 211,
        # Special cases (checked first)
        'mega hyper rare': 1260,
    }

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1,
        },
        "slot_2": {
            "illustration rare": 1 / 9, 
            "special illustration rare": 1 / 80,
            "mega hyper rare": 1 / 1260,
            "regular reverse": 1 - (1 / 9) - (1 / 80) - (1 / 1260),# ≈ 0.888888
        }
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

