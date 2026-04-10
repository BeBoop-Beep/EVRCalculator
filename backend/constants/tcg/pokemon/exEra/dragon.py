from .baseConfig import BaseSetConfig

class SetDragonConfig(BaseSetConfig):
    SET_NAME = 'Dragon'
    SET_ABBREVIATION = 'DR'

    SET_ID = 'ex3'
    RELEASE_DATE = '2003/11/24'
    PRINTED_TOTAL = 97
    TOTAL = 100
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1376/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1376/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
