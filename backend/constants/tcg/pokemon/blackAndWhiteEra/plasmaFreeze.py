from .baseConfig import BaseSetConfig

class SetPlasmaFreezeConfig(BaseSetConfig):
    SET_NAME = 'Plasma Freeze'
    SET_ABBREVIATION = 'PLF'

    SET_ID = 'bw9'
    RELEASE_DATE = '2013/05/08'
    PRINTED_TOTAL = 116
    TOTAL = 122
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw9/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw9/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
