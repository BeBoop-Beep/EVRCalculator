from .baseConfig import BaseSetConfig

class SetGymChallengeConfig(BaseSetConfig):
    SET_NAME = 'Gym Challenge'
    SET_ABBREVIATION = 'G2'

    SET_ID = 'gym2'
    RELEASE_DATE = '2000/10/16'
    PRINTED_TOTAL = 132
    TOTAL = 132
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/gym2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/gym2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
