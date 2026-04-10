from .baseConfig import BaseSetConfig

class SetTeamRocketReturnsConfig(BaseSetConfig):
    SET_NAME = 'Team Rocket Returns'
    SET_ABBREVIATION = 'TRR'

    SET_ID = 'ex7'
    RELEASE_DATE = '2004/11/01'
    PRINTED_TOTAL = 109
    TOTAL = 111
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex7/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex7/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
