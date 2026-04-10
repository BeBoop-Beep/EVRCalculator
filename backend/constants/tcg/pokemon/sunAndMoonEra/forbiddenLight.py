from .baseConfig import BaseSetConfig

class SetForbiddenLightConfig(BaseSetConfig):
    SET_NAME = 'Forbidden Light'
    SET_ABBREVIATION = 'FLI'

    SET_ID = 'sm6'
    RELEASE_DATE = '2018/05/04'
    PRINTED_TOTAL = 131
    TOTAL = 150
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm6/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm6/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
