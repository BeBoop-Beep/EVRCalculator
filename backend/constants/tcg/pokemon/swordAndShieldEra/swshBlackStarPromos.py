from .baseConfig import BaseSetConfig

class SetSwshBlackStarPromosConfig(BaseSetConfig):
    SET_NAME = 'SWSH Black Star Promos'
    SET_ABBREVIATION = 'PR-SW'

    SET_ID = 'swshp'
    RELEASE_DATE = '2019/11/15'
    PRINTED_TOTAL = 307
    TOTAL = 304
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swshp/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swshp/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
