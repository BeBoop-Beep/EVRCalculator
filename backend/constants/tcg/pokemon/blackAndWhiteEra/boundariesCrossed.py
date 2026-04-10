from .baseConfig import BaseSetConfig

class SetBoundariesCrossedConfig(BaseSetConfig):
    SET_NAME = 'Boundaries Crossed'
    SET_ABBREVIATION = 'BCR'

    SET_ID = 'bw7'
    RELEASE_DATE = '2012/11/07'
    PRINTED_TOTAL = 149
    TOTAL = 153
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw7/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw7/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
