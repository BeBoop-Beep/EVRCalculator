from .baseConfig import BaseSetConfig

class SetNextDestiniesConfig(BaseSetConfig):
    SET_NAME = 'Next Destinies'
    SET_ABBREVIATION = 'NXD'

    SET_ID = 'bw4'
    RELEASE_DATE = '2012/02/08'
    PRINTED_TOTAL = 99
    TOTAL = 103
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
