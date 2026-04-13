from .baseConfig import BaseSetConfig

class SetFusionStrikeConfig(BaseSetConfig):
    SET_NAME = 'Fusion Strike'
    SET_ABBREVIATION = 'FST'

    SET_ID = 'swsh8'
    RELEASE_DATE = '2021/11/12'
    PRINTED_TOTAL = 264
    TOTAL = 284
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh8/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh8/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2906/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2906/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
