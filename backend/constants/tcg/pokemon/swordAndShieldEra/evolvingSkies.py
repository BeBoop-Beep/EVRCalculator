from .baseConfig import BaseSetConfig

class SetEvolvingSkiesConfig(BaseSetConfig):
    SET_NAME = 'Evolving Skies'
    SET_ABBREVIATION = 'EVS'

    SET_ID = 'swsh7'
    RELEASE_DATE = '2021/08/27'
    PRINTED_TOTAL = 203
    TOTAL = 237
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh7/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh7/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2848/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2848/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
