from .baseConfig import BaseSetConfig

class SetCrystalGuardiansConfig(BaseSetConfig):
    SET_NAME = 'Crystal Guardians'
    SET_ABBREVIATION = 'CG'

    SET_ID = 'ex14'
    RELEASE_DATE = '2006/08/01'
    PRINTED_TOTAL = 100
    TOTAL = 100
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex14/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex14/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
