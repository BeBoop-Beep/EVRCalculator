from .baseConfig import BaseSetConfig

class SetMajesticDawnConfig(BaseSetConfig):
    SET_NAME = 'Majestic Dawn'
    SET_ABBREVIATION = 'MD'

    SET_ID = 'dp5'
    RELEASE_DATE = '2008/05/01'
    PRINTED_TOTAL = 100
    TOTAL = 100
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/dp5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/dp5/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
