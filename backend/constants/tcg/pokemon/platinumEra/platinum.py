from .baseConfig import BaseSetConfig

class SetPlatinumConfig(BaseSetConfig):
    SET_NAME = 'Platinum'
    SET_ABBREVIATION = 'PL'

    SET_ID = 'pl1'
    RELEASE_DATE = '2009/02/11'
    PRINTED_TOTAL = 127
    TOTAL = 133
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/pl1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/pl1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
