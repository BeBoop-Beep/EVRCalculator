from .baseConfig import BaseSetConfig

class SetBaseConfig(BaseSetConfig):
    SET_NAME = 'Base'
    SET_ABBREVIATION = 'BS'

    SET_ID = 'base1'
    RELEASE_DATE = '1999/01/09'
    PRINTED_TOTAL = 102
    TOTAL = 102
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/base1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/base1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/604/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/604/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
