from .baseConfig import BaseSetConfig

class SetFuriousFistsConfig(BaseSetConfig):
    SET_NAME = 'Furious Fists'
    SET_ABBREVIATION = 'FFI'

    SET_ID = 'xy3'
    RELEASE_DATE = '2014/08/13'
    PRINTED_TOTAL = 111
    TOTAL = 114
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/xy3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/xy3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
