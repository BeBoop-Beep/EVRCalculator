from .baseConfig import BaseSetConfig

class SetDetectivePikachuConfig(BaseSetConfig):
    SET_NAME = 'Detective Pikachu'
    SET_ABBREVIATION = 'DET'

    SET_ID = 'det1'
    RELEASE_DATE = '2019/04/05'
    PRINTED_TOTAL = 18
    TOTAL = 18
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/det1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/det1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2409/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2409/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
