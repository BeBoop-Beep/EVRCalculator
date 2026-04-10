from .baseConfig import BaseSetConfig

class SetTeamRocketConfig(BaseSetConfig):
    SET_NAME = 'Team Rocket'
    SET_ABBREVIATION = 'TR'

    SET_ID = 'base5'
    RELEASE_DATE = '2000/04/24'
    PRINTED_TOTAL = 82
    TOTAL = 83
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/base5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/base5/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
