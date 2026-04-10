from .baseConfig import BaseSetConfig

class SetMcdonaldSCollection2015Config(BaseSetConfig):
    SET_NAME = "McDonald's Collection 2015"
    SET_ABBREVIATION = None

    SET_ID = 'mcd15'
    RELEASE_DATE = '2015/11/27'
    PRINTED_TOTAL = 12
    TOTAL = 12
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/mcd15/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/mcd15/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1694/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1694/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
