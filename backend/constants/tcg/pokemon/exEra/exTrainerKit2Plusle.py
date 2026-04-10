from .baseConfig import BaseSetConfig

class SetExTrainerKit2PlusleConfig(BaseSetConfig):
    SET_NAME = 'EX Trainer Kit 2 Plusle'
    SET_ABBREVIATION = None

    SET_ID = 'tk2a'
    RELEASE_DATE = '2006/03/01'
    PRINTED_TOTAL = 12
    TOTAL = 12
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/tk2a/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/tk2a/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
