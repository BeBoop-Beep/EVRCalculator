from .baseConfig import BaseSetConfig

class SetAquapolisConfig(BaseSetConfig):
    SET_NAME = 'Aquapolis'
    SET_ABBREVIATION = 'AQ'

    SET_ID = 'ecard2'
    RELEASE_DATE = '2003/01/15'
    PRINTED_TOTAL = 147
    TOTAL = 182
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ecard2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ecard2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1397/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1397/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
