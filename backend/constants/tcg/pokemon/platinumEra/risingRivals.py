from .baseConfig import BaseSetConfig

class SetRisingRivalsConfig(BaseSetConfig):
    SET_NAME = 'Rising Rivals'
    SET_ABBREVIATION = 'RR'

    SET_ID = 'pl2'
    RELEASE_DATE = '2009/05/16'
    PRINTED_TOTAL = 111
    TOTAL = 120
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/pl2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/pl2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
