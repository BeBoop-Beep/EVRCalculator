from .baseConfig import BaseSetConfig

class SetSouthernIslandsConfig(BaseSetConfig):
    SET_NAME = 'Southern Islands'
    SET_ABBREVIATION = None

    SET_ID = 'si1'
    RELEASE_DATE = '2001/07/31'
    PRINTED_TOTAL = 18
    TOTAL = 18
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/si1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/si1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/648/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/648/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
