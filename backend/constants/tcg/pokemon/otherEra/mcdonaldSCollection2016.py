from .baseConfig import BaseSetConfig

class SetMcdonaldSCollection2016Config(BaseSetConfig):
    SET_NAME = "McDonald's Collection 2016"
    SET_ABBREVIATION = None

    SET_ID = 'mcd16'
    RELEASE_DATE = '2016/08/19'
    PRINTED_TOTAL = 12
    TOTAL = 12
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/mcd16/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/mcd16/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
