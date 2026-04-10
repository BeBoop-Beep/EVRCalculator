from .baseConfig import BaseSetConfig

class SetMcdonaldSCollection2021Config(BaseSetConfig):
    SET_NAME = "McDonald's Collection 2021"
    SET_ABBREVIATION = None

    SET_ID = 'mcd21'
    RELEASE_DATE = '2021/02/09'
    PRINTED_TOTAL = 25
    TOTAL = 25
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/mcd21/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/mcd21/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
