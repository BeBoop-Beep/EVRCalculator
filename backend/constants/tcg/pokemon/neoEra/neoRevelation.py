from .baseConfig import BaseSetConfig

class SetNeoRevelationConfig(BaseSetConfig):
    SET_NAME = 'Neo Revelation'
    SET_ABBREVIATION = 'N3'

    SET_ID = 'neo3'
    RELEASE_DATE = '2001/09/21'
    PRINTED_TOTAL = 64
    TOTAL = 66
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/neo3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/neo3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1389/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1389/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
