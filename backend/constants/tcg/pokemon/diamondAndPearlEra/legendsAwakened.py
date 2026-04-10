from .baseConfig import BaseSetConfig

class SetLegendsAwakenedConfig(BaseSetConfig):
    SET_NAME = 'Legends Awakened'
    SET_ABBREVIATION = 'LA'

    SET_ID = 'dp6'
    RELEASE_DATE = '2008/08/01'
    PRINTED_TOTAL = 146
    TOTAL = 146
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/dp6/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/dp6/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
