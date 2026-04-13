from .baseConfig import BaseSetConfig

class SetUnseenForcesConfig(BaseSetConfig):
    SET_NAME = 'Unseen Forces'
    SET_ABBREVIATION = 'UF'

    SET_ID = 'ex10'
    RELEASE_DATE = '2005/08/01'
    PRINTED_TOTAL = 115
    TOTAL = 145
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex10/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex10/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1398/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1398/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
