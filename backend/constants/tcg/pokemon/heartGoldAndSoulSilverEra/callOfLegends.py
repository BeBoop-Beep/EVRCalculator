from .baseConfig import BaseSetConfig

class SetCallOfLegendsConfig(BaseSetConfig):
    SET_NAME = 'Call of Legends'
    SET_ABBREVIATION = 'CL'

    SET_ID = 'col1'
    RELEASE_DATE = '2011/02/09'
    PRINTED_TOTAL = 95
    TOTAL = 106
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/col1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/col1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1415/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1415/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
