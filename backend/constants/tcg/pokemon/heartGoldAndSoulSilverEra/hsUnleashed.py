from .baseConfig import BaseSetConfig

class SetHsUnleashedConfig(BaseSetConfig):
    SET_NAME = 'HS—Unleashed'
    SET_ABBREVIATION = 'UL'

    SET_ID = 'hgss2'
    RELEASE_DATE = '2010/05/12'
    PRINTED_TOTAL = 95
    TOTAL = 96
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/hgss2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/hgss2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
