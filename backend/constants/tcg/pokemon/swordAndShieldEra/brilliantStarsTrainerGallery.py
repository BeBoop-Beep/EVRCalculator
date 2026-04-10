from .baseConfig import BaseSetConfig

class SetBrilliantStarsTrainerGalleryConfig(BaseSetConfig):
    SET_NAME = 'Brilliant Stars Trainer Gallery'
    SET_ABBREVIATION = 'BRS'

    SET_ID = 'swsh9tg'
    RELEASE_DATE = '2022/02/25'
    PRINTED_TOTAL = 30
    TOTAL = 30
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh9tg/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh9tg/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
