from .baseConfig import BaseSetConfig


class SetGenerationsRadiantCollectionConfig(BaseSetConfig):
    SET_NAME = 'Generations: Radiant Collection'
    SET_ABBREVIATION = None

    # SET_ID means Pokemon API set ID; this catalog has no unique API match.
    SET_ID = None
    RELEASE_DATE = None
    PRINTED_TOTAL = None
    TOTAL = None
    SYMBOL_IMAGE_URL = None
    LOGO_IMAGE_URL = None

    # Authoritative TCGplayer catalog identity from the cold-start baseline.
    TCGPLAYER_SET_ID = '1729'
    TCGPLAYER_SET_NAME = 'Generations: Radiant Collection'

    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1729/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1729/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # Historical catalog identity added for market/card coverage only.
    # It is NOT an approved pack-simulation product.
    PARENT_OPENING_SET_KEY = "generations"
    IS_SUBSET = True
    SUBSET_TYPE = "radiant_collection"
    COUNTS_TOWARD_PARENT_SET_VALUE = True
    COUNTS_TOWARD_PARENT_OPENING = True
    CATALOG_ONLY = False
    SUPPORTS_OPENING_SIMULATION = False
    USE_MONTE_CARLO_V2 = False
    PULL_MODEL_STATUS = "unsupported"
    PULL_RATE_MAPPING = {}
