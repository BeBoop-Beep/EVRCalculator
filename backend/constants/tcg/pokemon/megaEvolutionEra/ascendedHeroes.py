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

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}

    @classmethod
    def get_pack_state_overrides(cls):
        return get_ascended_heroes_pack_state_overrides()
