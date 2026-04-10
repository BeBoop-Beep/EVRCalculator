from .baseConfig import BaseSetConfig

class SetPopSeries1Config(BaseSetConfig):
    SET_NAME = 'POP Series 1'
    SET_ABBREVIATION = None

    SET_ID = 'pop1'
    RELEASE_DATE = '2004/09/01'
    PRINTED_TOTAL = 17
    TOTAL = 17
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/pop1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/pop1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1422/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1422/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
