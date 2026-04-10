from .baseConfig import BaseSetConfig

class SetPopSeries4Config(BaseSetConfig):
    SET_NAME = 'POP Series 4'
    SET_ABBREVIATION = None

    SET_ID = 'pop4'
    RELEASE_DATE = '2006/08/01'
    PRINTED_TOTAL = 17
    TOTAL = 17
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/pop4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/pop4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
