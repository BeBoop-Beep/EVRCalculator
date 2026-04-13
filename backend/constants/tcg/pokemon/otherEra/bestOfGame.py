from .baseConfig import BaseSetConfig

class SetBestOfGameConfig(BaseSetConfig):
    SET_NAME = 'Best of Game'
    SET_ABBREVIATION = 'BP'

    SET_ID = 'bp'
    RELEASE_DATE = '2002/12/01'
    PRINTED_TOTAL = 9
    TOTAL = 9
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bp/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bp/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
