from .baseConfig import BaseSetConfig

class SetCelebrationsClassicCollectionConfig(BaseSetConfig):
    PARENT_SET_KEY = "celebrations"
    IS_SUBSET = True
    SUBSET_TYPE = "classic_collection"
    COUNTS_TOWARD_PARENT_SET_VALUE = True
    COUNTS_TOWARD_PARENT_OPENING = True
    SUPPORTS_OPENING_SIMULATION = False
    SET_NAME = 'Celebrations: Classic Collection'
    SET_ABBREVIATION = 'CEL'

    SET_ID = 'cel25c'
    RELEASE_DATE = '2021/10/08'
    PRINTED_TOTAL = 25
    TOTAL = 25
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/cel25c/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/cel25c/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2931/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2931/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
