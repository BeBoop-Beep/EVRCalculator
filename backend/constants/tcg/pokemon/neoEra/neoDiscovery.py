from .baseConfig import BaseSetConfig

class SetNeoDiscoveryConfig(BaseSetConfig):
    SET_NAME = 'Neo Discovery'
    SET_ABBREVIATION = 'N2'

    SET_ID = 'neo2'
    RELEASE_DATE = '2001/06/01'
    PRINTED_TOTAL = 75
    TOTAL = 75
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/neo2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/neo2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
