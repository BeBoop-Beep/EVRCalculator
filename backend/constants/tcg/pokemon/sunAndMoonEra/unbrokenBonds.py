from .baseConfig import BaseSetConfig

class SetUnbrokenBondsConfig(BaseSetConfig):
    SET_NAME = 'Unbroken Bonds'
    SET_ABBREVIATION = 'UNB'

    SET_ID = 'sm10'
    RELEASE_DATE = '2019/05/03'
    PRINTED_TOTAL = 214
    TOTAL = 234
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm10/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm10/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2420/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2420/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
