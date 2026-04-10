from .baseConfig import BaseSetConfig

class SetCelebrationsConfig(BaseSetConfig):
    SET_NAME = 'Celebrations'
    SET_ABBREVIATION = 'CEL'

    SET_ID = 'cel25'
    RELEASE_DATE = '2021/10/08'
    PRINTED_TOTAL = 25
    TOTAL = 25
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/cel25/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/cel25/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
