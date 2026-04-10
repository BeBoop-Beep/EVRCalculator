from .baseConfig import BaseSetConfig

class SetSilverTempestConfig(BaseSetConfig):
    SET_NAME = 'Silver Tempest'
    SET_ABBREVIATION = 'SIT'

    SET_ID = 'swsh12'
    RELEASE_DATE = '2022/11/11'
    PRINTED_TOTAL = 195
    TOTAL = 215
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh12/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh12/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
