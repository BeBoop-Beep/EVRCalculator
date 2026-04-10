from .baseConfig import BaseSetConfig

class SetExTrainerKitLatiasConfig(BaseSetConfig):
    SET_NAME = 'EX Trainer Kit Latias'
    SET_ABBREVIATION = None

    SET_ID = 'tk1a'
    RELEASE_DATE = '2004/06/01'
    PRINTED_TOTAL = 10
    TOTAL = 10
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/tk1a/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/tk1a/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
