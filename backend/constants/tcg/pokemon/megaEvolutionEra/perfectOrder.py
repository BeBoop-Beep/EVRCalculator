from .baseConfig import BaseSetConfig

class SetPerfectOrderConfig(BaseSetConfig):
    SET_NAME = 'Perfect Order'
    SET_ABBREVIATION = 'POR'

    SET_ID = 'me3'
    RELEASE_DATE = '2026/03/27'
    PRINTED_TOTAL = 88
    TOTAL = 124
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/me3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/me3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
