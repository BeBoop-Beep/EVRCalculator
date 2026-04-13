from .baseConfig import BaseSetConfig

class SetBrilliantStarsConfig(BaseSetConfig):
    SET_NAME = 'Brilliant Stars'
    SET_ABBREVIATION = 'BRS'

    SET_ID = 'swsh9'
    RELEASE_DATE = '2022/02/25'
    PRINTED_TOTAL = 172
    TOTAL = 186
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh9/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh9/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2948/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2948/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
