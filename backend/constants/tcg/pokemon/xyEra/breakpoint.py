from .baseConfig import BaseSetConfig

class SetBreakpointConfig(BaseSetConfig):
    SET_NAME = 'BREAKpoint'
    SET_ABBREVIATION = 'BKP'

    SET_ID = 'xy9'
    RELEASE_DATE = '2016/02/03'
    PRINTED_TOTAL = 122
    TOTAL = 126
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy9/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy9/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1701/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1701/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
