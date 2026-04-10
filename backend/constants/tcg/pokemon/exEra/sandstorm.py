from .baseConfig import BaseSetConfig

class SetSandstormConfig(BaseSetConfig):
    SET_NAME = 'Sandstorm'
    SET_ABBREVIATION = 'SS'

    SET_ID = 'ex2'
    RELEASE_DATE = '2003/09/18'
    PRINTED_TOTAL = 100
    TOTAL = 100
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1392/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1392/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
