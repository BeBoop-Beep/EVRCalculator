from .baseConfig import BaseSetConfig

class SetLostOriginConfig(BaseSetConfig):
    SET_NAME = 'Lost Origin'
    SET_ABBREVIATION = 'LOR'

    SET_ID = 'swsh11'
    RELEASE_DATE = '2022/09/09'
    PRINTED_TOTAL = 196
    TOTAL = 217
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh11/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh11/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/3118/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/3118/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
