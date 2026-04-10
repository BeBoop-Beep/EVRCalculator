from .baseConfig import BaseSetConfig

class SetPlasmaBlastConfig(BaseSetConfig):
    SET_NAME = 'Plasma Blast'
    SET_ABBREVIATION = 'PLB'

    SET_ID = 'bw10'
    RELEASE_DATE = '2013/08/14'
    PRINTED_TOTAL = 101
    TOTAL = 105
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw10/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw10/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
