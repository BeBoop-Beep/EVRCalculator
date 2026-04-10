from .baseConfig import BaseSetConfig

class SetDragonMajestyConfig(BaseSetConfig):
    SET_NAME = 'Dragon Majesty'
    SET_ABBREVIATION = 'DRM'

    SET_ID = 'sm75'
    RELEASE_DATE = '2018/09/07'
    PRINTED_TOTAL = 70
    TOTAL = 80
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm75/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm75/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2295/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2295/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
