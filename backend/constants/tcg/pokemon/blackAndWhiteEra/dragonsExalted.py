from .baseConfig import BaseSetConfig

class SetDragonsExaltedConfig(BaseSetConfig):
    SET_NAME = 'Dragons Exalted'
    SET_ABBREVIATION = 'DRX'

    SET_ID = 'bw6'
    RELEASE_DATE = '2012/08/15'
    PRINTED_TOTAL = 124
    TOTAL = 128
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw6/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw6/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1394/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1394/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
