from .baseConfig import BaseSetConfig

class SetBwBlackStarPromosConfig(BaseSetConfig):
    SET_NAME = 'BW Black Star Promos'
    SET_ABBREVIATION = 'PR-BLW'

    SET_ID = 'bwp'
    RELEASE_DATE = '2011/03/01'
    PRINTED_TOTAL = 101
    TOTAL = 101
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bwp/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bwp/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
