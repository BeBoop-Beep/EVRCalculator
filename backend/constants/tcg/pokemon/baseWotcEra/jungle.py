from .baseConfig import BaseSetConfig

class SetJungleConfig(BaseSetConfig):
    SET_NAME = 'Jungle'
    SET_ABBREVIATION = 'JU'

    SET_ID = 'base2'
    RELEASE_DATE = '1999/06/16'
    PRINTED_TOTAL = 64
    TOTAL = 64
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/base2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/base2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
