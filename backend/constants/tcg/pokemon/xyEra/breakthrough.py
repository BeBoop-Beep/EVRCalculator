from .baseConfig import BaseSetConfig

class SetBreakthroughConfig(BaseSetConfig):
    SET_NAME = 'BREAKthrough'
    SET_ABBREVIATION = 'BKT'

    SET_ID = 'xy8'
    RELEASE_DATE = '2015/11/04'
    PRINTED_TOTAL = 162
    TOTAL = 165
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy8/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy8/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1661/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1661/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
