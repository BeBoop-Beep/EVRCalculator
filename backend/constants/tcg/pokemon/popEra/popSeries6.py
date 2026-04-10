from .baseConfig import BaseSetConfig

class SetPopSeries6Config(BaseSetConfig):
    SET_NAME = 'POP Series 6'
    SET_ABBREVIATION = None

    SET_ID = 'pop6'
    RELEASE_DATE = '2007/09/01'
    PRINTED_TOTAL = 17
    TOTAL = 17
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/pop6/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/pop6/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
