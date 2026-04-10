from .baseConfig import BaseSetConfig

class SetUnifiedMindsConfig(BaseSetConfig):
    SET_NAME = 'Unified Minds'
    SET_ABBREVIATION = 'UNM'

    SET_ID = 'sm11'
    RELEASE_DATE = '2019/08/02'
    PRINTED_TOTAL = 236
    TOTAL = 260
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm11/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm11/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2464/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2464/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
