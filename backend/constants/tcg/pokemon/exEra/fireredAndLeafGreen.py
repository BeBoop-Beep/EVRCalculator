from .baseConfig import BaseSetConfig

class SetFireredAndLeafGreenConfig(BaseSetConfig):
    SET_NAME = 'FireRed & LeafGreen'
    SET_ABBREVIATION = 'RG'

    SET_ID = 'ex6'
    RELEASE_DATE = '2004/09/01'
    PRINTED_TOTAL = 112
    TOTAL = 116
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex6/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex6/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
