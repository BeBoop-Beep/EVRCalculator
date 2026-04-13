from .baseConfig import BaseSetConfig

class SetFatesCollideConfig(BaseSetConfig):
    SET_NAME = 'Fates Collide'
    SET_ABBREVIATION = 'FCO'

    SET_ID = 'xy10'
    RELEASE_DATE = '2016/05/02'
    PRINTED_TOTAL = 124
    TOTAL = 129
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy10/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy10/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1780/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1780/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
