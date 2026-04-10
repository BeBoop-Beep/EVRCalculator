from .baseConfig import BaseSetConfig

class SetNeoGenesisConfig(BaseSetConfig):
    SET_NAME = 'Neo Genesis'
    SET_ABBREVIATION = 'N1'

    SET_ID = 'neo1'
    RELEASE_DATE = '2000/12/16'
    PRINTED_TOTAL = 111
    TOTAL = 111
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/neo1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/neo1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
