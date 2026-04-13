from .baseConfig import BaseSetConfig

class SetDpBlackStarPromosConfig(BaseSetConfig):
    SET_NAME = 'DP Black Star Promos'
    SET_ABBREVIATION = 'PR-DPP'

    SET_ID = 'dpp'
    RELEASE_DATE = '2007/05/01'
    PRINTED_TOTAL = 56
    TOTAL = 56
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/dpp/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/dpp/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
