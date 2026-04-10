from .baseConfig import BaseSetConfig

class SetFlashfireConfig(BaseSetConfig):
    SET_NAME = 'Flashfire'
    SET_ABBREVIATION = 'FLF'

    SET_ID = 'xy2'
    RELEASE_DATE = '2014/05/07'
    PRINTED_TOTAL = 106
    TOTAL = 110
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
