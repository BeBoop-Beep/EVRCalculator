from .baseConfig import BaseSetConfig

class SetMcdonaldSCollection2011Config(BaseSetConfig):
    SET_NAME = "McDonald's Collection 2011"
    SET_ABBREVIATION = None

    SET_ID = 'mcd11'
    RELEASE_DATE = '2011/06/17'
    PRINTED_TOTAL = 12
    TOTAL = 12
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/mcd11/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/mcd11/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1401/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1401/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
