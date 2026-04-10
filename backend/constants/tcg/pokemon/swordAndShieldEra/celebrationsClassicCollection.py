from .baseConfig import BaseSetConfig

class SetCelebrationsClassicCollectionConfig(BaseSetConfig):
    SET_NAME = 'Celebrations: Classic Collection'
    SET_ABBREVIATION = 'CEL'

    SET_ID = 'cel25c'
    RELEASE_DATE = '2021/10/08'
    PRINTED_TOTAL = 25
    TOTAL = 25
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/cel25c/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/cel25c/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
