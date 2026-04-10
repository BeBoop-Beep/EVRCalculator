from .baseConfig import BaseSetConfig

class SetBurningShadowsConfig(BaseSetConfig):
    SET_NAME = 'Burning Shadows'
    SET_ABBREVIATION = 'BUS'

    SET_ID = 'sm3'
    RELEASE_DATE = '2017/08/05'
    PRINTED_TOTAL = 147
    TOTAL = 177
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
