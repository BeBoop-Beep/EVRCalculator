from .baseConfig import BaseSetConfig

class SetPhantomForcesConfig(BaseSetConfig):
    SET_NAME = 'Phantom Forces'
    SET_ABBREVIATION = 'PHF'

    SET_ID = 'xy4'
    RELEASE_DATE = '2014/11/05'
    PRINTED_TOTAL = 119
    TOTAL = 124
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
