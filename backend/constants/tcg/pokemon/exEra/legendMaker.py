from .baseConfig import BaseSetConfig

class SetLegendMakerConfig(BaseSetConfig):
    SET_NAME = 'Legend Maker'
    SET_ABBREVIATION = 'LM'

    SET_ID = 'ex12'
    RELEASE_DATE = '2006/02/01'
    PRINTED_TOTAL = 92
    TOTAL = 93
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex12/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex12/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1378/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1378/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
