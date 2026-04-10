from .baseConfig import BaseSetConfig

class SetCrownZenithGalarianGalleryConfig(BaseSetConfig):
    SET_NAME = 'Crown Zenith Galarian Gallery'
    SET_ABBREVIATION = 'CRZ'

    SET_ID = 'swsh12pt5gg'
    RELEASE_DATE = '2023/01/20'
    PRINTED_TOTAL = 70
    TOTAL = 70
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh12pt5gg/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh12pt5gg/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
