from .baseConfig import BaseSetConfig

class SetPhantasmalFlamesConfig(BaseSetConfig):
    SET_NAME = 'Phantasmal Flames'
    SET_ABBREVIATION = 'PFL'

    SET_ID = 'me2'
    RELEASE_DATE = '2025/11/14'
    PRINTED_TOTAL = 94
    TOTAL = 130
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/me2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/me2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24448/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24448/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
