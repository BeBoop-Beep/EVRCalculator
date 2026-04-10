from .baseConfig import BaseSetConfig

class SetGenerationsConfig(BaseSetConfig):
    SET_NAME = 'Generations'
    SET_ABBREVIATION = 'GEN'

    SET_ID = 'g1'
    RELEASE_DATE = '2016/02/22'
    PRINTED_TOTAL = 83
    TOTAL = 117
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/g1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/g1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
