from .baseConfig import BaseSetConfig

class SetRoaringSkiesConfig(BaseSetConfig):
    SET_NAME = 'Roaring Skies'
    SET_ABBREVIATION = 'ROS'

    SET_ID = 'xy6'
    RELEASE_DATE = '2015/05/06'
    PRINTED_TOTAL = 108
    TOTAL = 112
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy6/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy6/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
