from .baseConfig import BaseSetConfig

class SetBlackAndWhiteConfig(BaseSetConfig):
    SET_NAME = 'Black & White'
    SET_ABBREVIATION = 'BLW'

    SET_ID = 'bw1'
    RELEASE_DATE = '2011/04/25'
    PRINTED_TOTAL = 114
    TOTAL = 115
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1400/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1400/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
