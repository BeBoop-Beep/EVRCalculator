from .baseConfig import BaseSetConfig

class SetAstralRadianceTrainerGalleryConfig(BaseSetConfig):
    SET_NAME = 'Astral Radiance Trainer Gallery'
    SET_ABBREVIATION = 'ASR'

    SET_ID = 'swsh10tg'
    RELEASE_DATE = '2022/05/27'
    PRINTED_TOTAL = 30
    TOTAL = 30
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh10tg/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh10tg/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/3068/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/3068/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
