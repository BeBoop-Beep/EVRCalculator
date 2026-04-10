from .baseConfig import BaseSetConfig

class SetSkyridgeConfig(BaseSetConfig):
    SET_NAME = 'Skyridge'
    SET_ABBREVIATION = 'SK'

    SET_ID = 'ecard3'
    RELEASE_DATE = '2003/05/12'
    PRINTED_TOTAL = 144
    TOTAL = 182
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ecard3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ecard3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
