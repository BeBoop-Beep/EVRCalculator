from .baseConfig import BaseSetConfig

class SetMcdonaldSCollection2022Config(BaseSetConfig):
    SET_NAME = "McDonald's Collection 2022"
    SET_ABBREVIATION = None

    SET_ID = 'mcd22'
    RELEASE_DATE = '2022/08/03'
    PRINTED_TOTAL = 15
    TOTAL = 15
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/mcd22/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/mcd22/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
