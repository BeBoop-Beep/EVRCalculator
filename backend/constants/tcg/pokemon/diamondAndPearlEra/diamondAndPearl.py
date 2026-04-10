from .baseConfig import BaseSetConfig

class SetDiamondAndPearlConfig(BaseSetConfig):
    SET_NAME = 'Diamond & Pearl'
    SET_ABBREVIATION = 'DP'

    SET_ID = 'dp1'
    RELEASE_DATE = '2007/05/01'
    PRINTED_TOTAL = 130
    TOTAL = 130
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/dp1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/dp1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
