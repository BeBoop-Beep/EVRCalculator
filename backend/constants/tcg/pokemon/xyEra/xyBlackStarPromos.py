from .baseConfig import BaseSetConfig

class SetXyBlackStarPromosConfig(BaseSetConfig):
    SET_NAME = 'XY Black Star Promos'
    SET_ABBREVIATION = 'PR-XY'

    SET_ID = 'xyp'
    RELEASE_DATE = '2013/10/12'
    PRINTED_TOTAL = 211
    TOTAL = 216
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xyp/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xyp/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
