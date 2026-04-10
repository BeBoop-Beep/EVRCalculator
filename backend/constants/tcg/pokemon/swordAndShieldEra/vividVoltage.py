from .baseConfig import BaseSetConfig

class SetVividVoltageConfig(BaseSetConfig):
    SET_NAME = 'Vivid Voltage'
    SET_ABBREVIATION = 'VIV'

    SET_ID = 'swsh4'
    RELEASE_DATE = '2020/11/13'
    PRINTED_TOTAL = 185
    TOTAL = 203
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
