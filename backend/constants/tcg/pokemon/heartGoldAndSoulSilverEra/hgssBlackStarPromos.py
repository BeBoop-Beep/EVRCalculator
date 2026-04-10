from .baseConfig import BaseSetConfig

class SetHgssBlackStarPromosConfig(BaseSetConfig):
    SET_NAME = 'HGSS Black Star Promos'
    SET_ABBREVIATION = 'PR-HS'

    SET_ID = 'hsp'
    RELEASE_DATE = '2010/02/10'
    PRINTED_TOTAL = 25
    TOTAL = 25
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/hsp/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/hsp/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
