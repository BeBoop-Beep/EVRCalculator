from .baseConfig import BaseSetConfig

class SetHsTriumphantConfig(BaseSetConfig):
    SET_NAME = 'HS—Triumphant'
    SET_ABBREVIATION = 'TM'

    SET_ID = 'hgss4'
    RELEASE_DATE = '2010/11/03'
    PRINTED_TOTAL = 102
    TOTAL = 103
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/hgss4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/hgss4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1381/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1381/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
