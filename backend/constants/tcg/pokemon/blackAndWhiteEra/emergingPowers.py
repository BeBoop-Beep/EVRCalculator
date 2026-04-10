from .baseConfig import BaseSetConfig

class SetEmergingPowersConfig(BaseSetConfig):
    SET_NAME = 'Emerging Powers'
    SET_ABBREVIATION = 'EPO'

    SET_ID = 'bw2'
    RELEASE_DATE = '2011/08/31'
    PRINTED_TOTAL = 98
    TOTAL = 98
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw2/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw2/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
