from .baseConfig import BaseSetConfig

class SetSwordAndShieldConfig(BaseSetConfig):
    SET_NAME = 'Sword & Shield'
    SET_ABBREVIATION = 'SSH'

    SET_ID = 'swsh1'
    RELEASE_DATE = '2020/02/07'
    PRINTED_TOTAL = 202
    TOTAL = 216
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
