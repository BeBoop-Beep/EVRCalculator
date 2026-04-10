from .baseConfig import BaseSetConfig

class SetMcdonaldSCollection2018Config(BaseSetConfig):
    SET_NAME = "McDonald's Collection 2018"
    SET_ABBREVIATION = None

    SET_ID = 'mcd18'
    RELEASE_DATE = '2018/10/16'
    PRINTED_TOTAL = 12
    TOTAL = 12
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/mcd18/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/mcd18/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2364/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2364/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
