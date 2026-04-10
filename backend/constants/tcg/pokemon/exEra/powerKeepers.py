from .baseConfig import BaseSetConfig

class SetPowerKeepersConfig(BaseSetConfig):
    SET_NAME = 'Power Keepers'
    SET_ABBREVIATION = 'PK'

    SET_ID = 'ex16'
    RELEASE_DATE = '2007/02/02'
    PRINTED_TOTAL = 108
    TOTAL = 108
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex16/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex16/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
