from .baseConfig import BaseSetConfig

class SetEvolutionsConfig(BaseSetConfig):
    SET_NAME = 'Evolutions'
    SET_ABBREVIATION = 'EVO'

    SET_ID = 'xy12'
    RELEASE_DATE = '2016/11/02'
    PRINTED_TOTAL = 108
    TOTAL = 113
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy12/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy12/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
