from .baseConfig import BaseSetConfig

class SetNobleVictoriesConfig(BaseSetConfig):
    SET_NAME = 'Noble Victories'
    SET_ABBREVIATION = 'NVI'

    SET_ID = 'bw3'
    RELEASE_DATE = '2011/11/16'
    PRINTED_TOTAL = 101
    TOTAL = 102
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
