from .baseConfig import BaseSetConfig

class SetPopSeries9Config(BaseSetConfig):
    SET_NAME = 'POP Series 9'
    SET_ABBREVIATION = None

    SET_ID = 'pop9'
    RELEASE_DATE = '2009/03/01'
    PRINTED_TOTAL = 17
    TOTAL = 17
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/pop9/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/pop9/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1446/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1446/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
