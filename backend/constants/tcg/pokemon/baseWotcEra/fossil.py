from .baseConfig import BaseSetConfig

class SetFossilConfig(BaseSetConfig):
    SET_NAME = 'Fossil'
    SET_ABBREVIATION = 'FO'

    SET_ID = 'base3'
    RELEASE_DATE = '1999/10/10'
    PRINTED_TOTAL = 62
    TOTAL = 62
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/base3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/base3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/630/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/630/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
