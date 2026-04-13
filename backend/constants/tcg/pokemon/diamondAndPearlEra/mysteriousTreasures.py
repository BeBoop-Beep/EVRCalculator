from .baseConfig import BaseSetConfig

class SetMysteriousTreasuresConfig(BaseSetConfig):
    SET_NAME = 'Mysterious Treasures'
    SET_ABBREVIATION = 'MT'

    SET_ID = 'dp2'
    RELEASE_DATE = '2007/08/01'
    PRINTED_TOTAL = 123
    TOTAL = 124
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/dp2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/dp2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1368/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1368/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
