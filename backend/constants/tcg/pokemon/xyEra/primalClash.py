from .baseConfig import BaseSetConfig

class SetPrimalClashConfig(BaseSetConfig):
    SET_NAME = 'Primal Clash'
    SET_ABBREVIATION = 'PRC'

    SET_ID = 'xy5'
    RELEASE_DATE = '2015/02/04'
    PRINTED_TOTAL = 160
    TOTAL = 164
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy5/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
