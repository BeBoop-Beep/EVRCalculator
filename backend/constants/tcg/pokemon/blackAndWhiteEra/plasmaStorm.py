from .baseConfig import BaseSetConfig

class SetPlasmaStormConfig(BaseSetConfig):
    SET_NAME = 'Plasma Storm'
    SET_ABBREVIATION = 'PLS'

    SET_ID = 'bw8'
    RELEASE_DATE = '2013/02/06'
    PRINTED_TOTAL = 135
    TOTAL = 138
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw8/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw8/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
