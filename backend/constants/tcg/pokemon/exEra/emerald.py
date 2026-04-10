from .baseConfig import BaseSetConfig

class SetEmeraldConfig(BaseSetConfig):
    SET_NAME = 'Emerald'
    SET_ABBREVIATION = 'EM'

    SET_ID = 'ex9'
    RELEASE_DATE = '2005/05/01'
    PRINTED_TOTAL = 106
    TOTAL = 107
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex9/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex9/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1410/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1410/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
