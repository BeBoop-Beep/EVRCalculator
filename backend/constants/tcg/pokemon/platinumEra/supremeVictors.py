from .baseConfig import BaseSetConfig

class SetSupremeVictorsConfig(BaseSetConfig):
    SET_NAME = 'Supreme Victors'
    SET_ABBREVIATION = 'SV'

    SET_ID = 'pl3'
    RELEASE_DATE = '2009/08/19'
    PRINTED_TOTAL = 147
    TOTAL = 153
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/pl3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/pl3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
