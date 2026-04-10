from .baseConfig import BaseSetConfig

class SetStormfrontConfig(BaseSetConfig):
    SET_NAME = 'Stormfront'
    SET_ABBREVIATION = 'SF'

    SET_ID = 'dp7'
    RELEASE_DATE = '2008/11/01'
    PRINTED_TOTAL = 100
    TOTAL = 106
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/dp7/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/dp7/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1369/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1369/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
