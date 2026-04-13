from .baseConfig import BaseSetConfig

class SetLostOriginTrainerGalleryConfig(BaseSetConfig):
    SET_NAME = 'Lost Origin Trainer Gallery'
    SET_ABBREVIATION = 'LOR'

    SET_ID = 'swsh11tg'
    RELEASE_DATE = '2022/09/09'
    PRINTED_TOTAL = 30
    TOTAL = 30
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh11tg/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh11tg/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/3172/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/3172/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
