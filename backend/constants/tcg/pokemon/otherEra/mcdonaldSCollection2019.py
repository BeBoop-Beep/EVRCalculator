from .baseConfig import BaseSetConfig

class SetMcdonaldSCollection2019Config(BaseSetConfig):
    SET_NAME = "McDonald's Collection 2019"
    SET_ABBREVIATION = None

    SET_ID = 'mcd19'
    RELEASE_DATE = '2019/10/15'
    PRINTED_TOTAL = 12
    TOTAL = 12
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/mcd19/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/mcd19/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2555/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2555/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
