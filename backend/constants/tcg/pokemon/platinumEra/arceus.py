from .baseConfig import BaseSetConfig

class SetArceusConfig(BaseSetConfig):
    SET_NAME = 'Arceus'
    SET_ABBREVIATION = 'AR'

    SET_ID = 'pl4'
    RELEASE_DATE = '2009/11/04'
    PRINTED_TOTAL = 99
    TOTAL = 111
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/pl4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/pl4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
