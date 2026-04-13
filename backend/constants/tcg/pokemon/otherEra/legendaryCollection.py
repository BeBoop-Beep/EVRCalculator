from .baseConfig import BaseSetConfig

class SetLegendaryCollectionConfig(BaseSetConfig):
    SET_NAME = 'Legendary Collection'
    SET_ABBREVIATION = 'LC'

    SET_ID = 'base6'
    RELEASE_DATE = '2002/05/24'
    PRINTED_TOTAL = 110
    TOTAL = 110
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/base6/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/base6/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1374/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1374/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
