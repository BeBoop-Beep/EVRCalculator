from .baseConfig import BaseSetConfig

class SetSecretWondersConfig(BaseSetConfig):
    SET_NAME = 'Secret Wonders'
    SET_ABBREVIATION = 'SW'

    SET_ID = 'dp3'
    RELEASE_DATE = '2007/11/01'
    PRINTED_TOTAL = 132
    TOTAL = 132
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/dp3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/dp3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
