from .baseConfig import BaseSetConfig

class SetBaseSet2Config(BaseSetConfig):
    SET_NAME = 'Base Set 2'
    SET_ABBREVIATION = 'B2'

    SET_ID = 'base4'
    RELEASE_DATE = '2000/02/24'
    PRINTED_TOTAL = 130
    TOTAL = 130
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/base4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/base4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/605/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/605/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
