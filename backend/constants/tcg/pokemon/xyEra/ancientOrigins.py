from .baseConfig import BaseSetConfig

class SetAncientOriginsConfig(BaseSetConfig):
    SET_NAME = 'Ancient Origins'
    SET_ABBREVIATION = 'AOR'

    SET_ID = 'xy7'
    RELEASE_DATE = '2015/08/12'
    PRINTED_TOTAL = 98
    TOTAL = 100
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy7/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy7/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1576/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1576/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
