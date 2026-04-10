from .baseConfig import BaseSetConfig

class SetHiddenLegendsConfig(BaseSetConfig):
    SET_NAME = 'Hidden Legends'
    SET_ABBREVIATION = 'HL'

    SET_ID = 'ex5'
    RELEASE_DATE = '2004/06/01'
    PRINTED_TOTAL = 101
    TOTAL = 102
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex5/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1416/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1416/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
