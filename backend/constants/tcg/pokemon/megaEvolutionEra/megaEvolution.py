from .baseConfig import BaseSetConfig

class SetMegaEvolutionConfig(BaseSetConfig):
    SET_NAME = 'Mega Evolution'
    SET_ABBREVIATION = 'MEG'

    SET_ID = 'me1'
    RELEASE_DATE = '2025/09/26'
    PRINTED_TOTAL = 132
    TOTAL = 188
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/me1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/me1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
