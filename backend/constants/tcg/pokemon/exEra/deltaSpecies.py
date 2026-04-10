from .baseConfig import BaseSetConfig

class SetDeltaSpeciesConfig(BaseSetConfig):
    SET_NAME = 'Delta Species'
    SET_ABBREVIATION = 'DS'

    SET_ID = 'ex11'
    RELEASE_DATE = '2005/10/31'
    PRINTED_TOTAL = 113
    TOTAL = 114
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex11/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex11/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
