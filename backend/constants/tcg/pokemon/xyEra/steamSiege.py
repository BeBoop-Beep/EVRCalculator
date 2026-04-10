from .baseConfig import BaseSetConfig

class SetSteamSiegeConfig(BaseSetConfig):
    SET_NAME = 'Steam Siege'
    SET_ABBREVIATION = 'STS'

    SET_ID = 'xy11'
    RELEASE_DATE = '2016/08/03'
    PRINTED_TOTAL = 114
    TOTAL = 116
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy11/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy11/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
