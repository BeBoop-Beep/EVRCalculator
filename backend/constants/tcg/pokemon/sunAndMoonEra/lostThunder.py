from .baseConfig import BaseSetConfig

class SetLostThunderConfig(BaseSetConfig):
    SET_NAME = 'Lost Thunder'
    SET_ABBREVIATION = 'LOT'

    SET_ID = 'sm8'
    RELEASE_DATE = '2018/11/02'
    PRINTED_TOTAL = 214
    TOTAL = 240
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm8/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm8/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
