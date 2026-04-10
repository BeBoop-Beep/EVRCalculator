from .baseConfig import BaseSetConfig

class SetKalosStarterSetConfig(BaseSetConfig):
    SET_NAME = 'Kalos Starter Set'
    SET_ABBREVIATION = 'KSS'

    SET_ID = 'xy0'
    RELEASE_DATE = '2013/11/08'
    PRINTED_TOTAL = 39
    TOTAL = 39
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy0/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy0/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
