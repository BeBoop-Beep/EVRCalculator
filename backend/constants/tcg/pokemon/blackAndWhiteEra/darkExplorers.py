from .baseConfig import BaseSetConfig

class SetDarkExplorersConfig(BaseSetConfig):
    SET_NAME = 'Dark Explorers'
    SET_ABBREVIATION = 'DEX'

    SET_ID = 'bw5'
    RELEASE_DATE = '2012/05/09'
    PRINTED_TOTAL = 108
    TOTAL = 111
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw5/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
