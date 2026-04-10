from .baseConfig import BaseSetConfig

class SetShiningFatesConfig(BaseSetConfig):
    SET_NAME = 'Shining Fates'
    SET_ABBREVIATION = 'SHF'

    SET_ID = 'swsh45'
    RELEASE_DATE = '2021/02/19'
    PRINTED_TOTAL = 72
    TOTAL = 73
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh45/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh45/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2754/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2754/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
