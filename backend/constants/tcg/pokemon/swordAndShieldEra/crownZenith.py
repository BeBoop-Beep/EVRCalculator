from .baseConfig import BaseSetConfig

class SetCrownZenithConfig(BaseSetConfig):
    SET_NAME = 'Crown Zenith'
    SET_ABBREVIATION = 'CRZ'

    SET_ID = 'swsh12pt5'
    RELEASE_DATE = '2023/01/20'
    PRINTED_TOTAL = 159
    TOTAL = 160
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh12pt5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh12pt5/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/17688/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/17688/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
