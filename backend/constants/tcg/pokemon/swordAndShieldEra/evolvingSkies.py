from .baseConfig import BaseSetConfig

class SetEvolvingSkiesConfig(BaseSetConfig):
    SET_NAME = 'Evolving Skies'
    SET_ABBREVIATION = 'EVS'

    SET_ID = 'swsh7'
    RELEASE_DATE = '2021/08/27'
    PRINTED_TOTAL = 203
    TOTAL = 237
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh7/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh7/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
