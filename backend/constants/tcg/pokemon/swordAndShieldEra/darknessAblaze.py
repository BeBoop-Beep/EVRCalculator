from .baseConfig import BaseSetConfig

class SetDarknessAblazeConfig(BaseSetConfig):
    SET_NAME = 'Darkness Ablaze'
    SET_ABBREVIATION = 'DAA'

    SET_ID = 'swsh3'
    RELEASE_DATE = '2020/08/14'
    PRINTED_TOTAL = 189
    TOTAL = 201
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2675/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2675/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
