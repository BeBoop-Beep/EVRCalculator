from .baseConfig import BaseSetConfig

class SetSmBlackStarPromosConfig(BaseSetConfig):
    SET_NAME = 'SM Black Star Promos'
    SET_ABBREVIATION = 'PR-SM'

    SET_ID = 'smp'
    RELEASE_DATE = '2017/02/03'
    PRINTED_TOTAL = 248
    TOTAL = 250
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/smp/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/smp/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
