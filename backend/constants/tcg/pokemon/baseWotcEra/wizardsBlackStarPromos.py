from .baseConfig import BaseSetConfig

class SetWizardsBlackStarPromosConfig(BaseSetConfig):
    SET_NAME = 'Wizards Black Star Promos'
    SET_ABBREVIATION = 'PR'

    SET_ID = 'basep'
    RELEASE_DATE = '1999/07/01'
    PRINTED_TOTAL = 53
    TOTAL = 53
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/basep/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/basep/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
