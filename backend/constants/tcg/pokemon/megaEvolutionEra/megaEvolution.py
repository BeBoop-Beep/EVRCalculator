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

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}

    @classmethod
    def get_pack_state_overrides(cls):
        return get_mega_evolution_pack_state_overrides()
