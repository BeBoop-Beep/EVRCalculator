from .baseConfig import BaseSetConfig

class SetGuardiansRisingConfig(BaseSetConfig):
    SET_NAME = 'Guardians Rising'
    SET_ABBREVIATION = 'GRI'

    SET_ID = 'sm2'
    RELEASE_DATE = '2017/05/05'
    PRINTED_TOTAL = 145
    TOTAL = 180
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
