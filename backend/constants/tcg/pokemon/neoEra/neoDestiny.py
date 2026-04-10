from .baseConfig import BaseSetConfig

class SetNeoDestinyConfig(BaseSetConfig):
    SET_NAME = 'Neo Destiny'
    SET_ABBREVIATION = 'N4'

    SET_ID = 'neo4'
    RELEASE_DATE = '2002/02/28'
    PRINTED_TOTAL = 105
    TOTAL = 113
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/neo4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/neo4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
