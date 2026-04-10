from .baseConfig import BaseSetConfig

class SetHiddenFatesConfig(BaseSetConfig):
    SET_NAME = 'Hidden Fates'
    SET_ABBREVIATION = 'HIF'

    SET_ID = 'sm115'
    RELEASE_DATE = '2019/08/23'
    PRINTED_TOTAL = 68
    TOTAL = 69
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm115/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm115/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
