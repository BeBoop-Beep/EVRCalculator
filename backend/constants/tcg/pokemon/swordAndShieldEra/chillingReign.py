from .baseConfig import BaseSetConfig

class SetChillingReignConfig(BaseSetConfig):
    SET_NAME = 'Chilling Reign'
    SET_ABBREVIATION = 'CRE'

    SET_ID = 'swsh6'
    RELEASE_DATE = '2021/06/18'
    PRINTED_TOTAL = 198
    TOTAL = 233
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh6/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh6/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2807/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2807/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
