from .baseConfig import BaseSetConfig

class SetExTrainerKitLatiosConfig(BaseSetConfig):
    SET_NAME = 'EX Trainer Kit Latios'
    SET_ABBREVIATION = None

    SET_ID = 'tk1b'
    RELEASE_DATE = '2004/06/01'
    PRINTED_TOTAL = 10
    TOTAL = 10
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/tk1b/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/tk1b/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
