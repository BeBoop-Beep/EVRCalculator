from .baseConfig import BaseSetConfig

class SetHolonPhantomsConfig(BaseSetConfig):
    SET_NAME = 'Holon Phantoms'
    SET_ABBREVIATION = 'HP'

    SET_ID = 'ex13'
    RELEASE_DATE = '2006/05/01'
    PRINTED_TOTAL = 110
    TOTAL = 111
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex13/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex13/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
