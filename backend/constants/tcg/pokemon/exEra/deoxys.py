from .baseConfig import BaseSetConfig

class SetDeoxysConfig(BaseSetConfig):
    SET_NAME = 'Deoxys'
    SET_ABBREVIATION = 'DX'

    SET_ID = 'ex8'
    RELEASE_DATE = '2005/02/01'
    PRINTED_TOTAL = 107
    TOTAL = 108
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex8/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex8/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
