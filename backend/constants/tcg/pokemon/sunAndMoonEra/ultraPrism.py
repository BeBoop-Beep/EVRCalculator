from .baseConfig import BaseSetConfig

class SetUltraPrismConfig(BaseSetConfig):
    SET_NAME = 'Ultra Prism'
    SET_ABBREVIATION = 'UPR'

    SET_ID = 'sm5'
    RELEASE_DATE = '2018/02/02'
    PRINTED_TOTAL = 156
    TOTAL = 178
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm5/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2178/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2178/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
