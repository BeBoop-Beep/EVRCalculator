from .baseConfig import BaseSetConfig

class SetSunAndMoonConfig(BaseSetConfig):
    SET_NAME = 'Sun & Moon'
    SET_ABBREVIATION = 'SUM'

    SET_ID = 'sm1'
    RELEASE_DATE = '2017/02/03'
    PRINTED_TOTAL = 149
    TOTAL = 173
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
