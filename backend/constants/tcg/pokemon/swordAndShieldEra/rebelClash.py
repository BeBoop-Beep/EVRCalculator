from .baseConfig import BaseSetConfig

class SetRebelClashConfig(BaseSetConfig):
    SET_NAME = 'Rebel Clash'
    SET_ABBREVIATION = 'RCL'

    SET_ID = 'swsh2'
    RELEASE_DATE = '2020/05/01'
    PRINTED_TOTAL = 192
    TOTAL = 209
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2626/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2626/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
