from .baseConfig import BaseSetConfig

class SetMcdonaldSCollection2017Config(BaseSetConfig):
    SET_NAME = "McDonald's Collection 2017"
    SET_ABBREVIATION = None

    SET_ID = 'mcd17'
    RELEASE_DATE = '2017/11/07'
    PRINTED_TOTAL = 12
    TOTAL = 12
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/mcd17/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/mcd17/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2148/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2148/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
