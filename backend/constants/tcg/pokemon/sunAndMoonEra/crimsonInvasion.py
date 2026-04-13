from .baseConfig import BaseSetConfig

class SetCrimsonInvasionConfig(BaseSetConfig):
    SET_NAME = 'Crimson Invasion'
    SET_ABBREVIATION = 'CIN'

    SET_ID = 'sm4'
    RELEASE_DATE = '2017/11/03'
    PRINTED_TOTAL = 111
    TOTAL = 126
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2071/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2071/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
