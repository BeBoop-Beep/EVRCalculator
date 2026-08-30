from .baseConfig import BaseSetConfig

class SetSilverTempestTrainerGalleryConfig(BaseSetConfig):
    PARENT_SET_KEY = "silverTempest"
    IS_SUBSET = True
    SUBSET_TYPE = "trainer_gallery"
    COUNTS_TOWARD_PARENT_SET_VALUE = True
    COUNTS_TOWARD_PARENT_OPENING = True
    SUPPORTS_OPENING_SIMULATION = False
    SET_NAME = 'Silver Tempest Trainer Gallery'
    SET_ABBREVIATION = 'SIT'

    SET_ID = 'swsh12tg'
    RELEASE_DATE = '2022/11/11'
    PRINTED_TOTAL = 30
    TOTAL = 30
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh12tg/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh12tg/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/17674/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/17674/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
