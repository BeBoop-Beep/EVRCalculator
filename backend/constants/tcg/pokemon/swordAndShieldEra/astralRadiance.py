from .baseConfig import BaseSetConfig

class SetAstralRadianceConfig(BaseSetConfig):
    SET_NAME = 'Astral Radiance'
    SET_ABBREVIATION = 'ASR'

    SET_ID = 'swsh10'
    RELEASE_DATE = '2022/05/27'
    PRINTED_TOTAL = 189
    TOTAL = 216
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh10/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh10/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
