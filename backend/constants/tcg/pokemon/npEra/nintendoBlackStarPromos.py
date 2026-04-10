from .baseConfig import BaseSetConfig

class SetNintendoBlackStarPromosConfig(BaseSetConfig):
    SET_NAME = 'Nintendo Black Star Promos'
    SET_ABBREVIATION = 'PR-NP'

    SET_ID = 'np'
    RELEASE_DATE = '2003/10/01'
    PRINTED_TOTAL = 40
    TOTAL = 40
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/np/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/np/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1423/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1423/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
