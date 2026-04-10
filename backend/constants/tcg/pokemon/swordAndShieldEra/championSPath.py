from .baseConfig import BaseSetConfig

class SetChampionSPathConfig(BaseSetConfig):
    SET_NAME = "Champion's Path"
    SET_ABBREVIATION = 'CPA'

    SET_ID = 'swsh35'
    RELEASE_DATE = '2020/09/25'
    PRINTED_TOTAL = 73
    TOTAL = 80
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh35/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh35/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
