from .baseConfig import BaseSetConfig

class SetLegendaryTreasuresConfig(BaseSetConfig):
    SET_NAME = 'Legendary Treasures'
    SET_ABBREVIATION = 'LTR'

    SET_ID = 'bw11'
    RELEASE_DATE = '2013/11/06'
    PRINTED_TOTAL = 113
    TOTAL = 140
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw11/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw11/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
