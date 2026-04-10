from .baseConfig import BaseSetConfig

class SetDoubleCrisisConfig(BaseSetConfig):
    SET_NAME = 'Double Crisis'
    SET_ABBREVIATION = 'DCR'

    SET_ID = 'dc1'
    RELEASE_DATE = '2015/03/25'
    PRINTED_TOTAL = 34
    TOTAL = 34
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/dc1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/dc1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
