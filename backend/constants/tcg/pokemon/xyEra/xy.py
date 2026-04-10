from .baseConfig import BaseSetConfig

class SetXyConfig(BaseSetConfig):
    SET_NAME = 'XY'
    SET_ABBREVIATION = 'XY'

    SET_ID = 'xy1'
    RELEASE_DATE = '2014/02/05'
    PRINTED_TOTAL = 146
    TOTAL = 146
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1387/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1387/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
