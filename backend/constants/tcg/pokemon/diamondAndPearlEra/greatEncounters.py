from .baseConfig import BaseSetConfig

class SetGreatEncountersConfig(BaseSetConfig):
    SET_NAME = 'Great Encounters'
    SET_ABBREVIATION = 'GE'

    SET_ID = 'dp4'
    RELEASE_DATE = '2008/02/01'
    PRINTED_TOTAL = 106
    TOTAL = 106
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/dp4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/dp4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1405/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1405/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
