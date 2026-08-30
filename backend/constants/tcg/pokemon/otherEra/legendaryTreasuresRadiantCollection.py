from .baseConfig import BaseSetConfig


class SetLegendaryTreasuresRadiantCollectionConfig(BaseSetConfig):
    SET_NAME = 'Legendary Treasures: Radiant Collection'
    SET_ABBREVIATION = None

    # SET_ID means Pokemon API set ID; this catalog has no unique API match.
    SET_ID = None
    RELEASE_DATE = None
    PRINTED_TOTAL = None
    TOTAL = None
    SYMBOL_IMAGE_URL = None
    LOGO_IMAGE_URL = None

    # Authoritative TCGplayer catalog identity from the cold-start baseline.
    TCGPLAYER_SET_ID = '1465'
    TCGPLAYER_SET_NAME = 'Legendary Treasures: Radiant Collection'

    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1465/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1465/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # Separately scraped child subset of Legendary Treasures.  Structural subset
    # state, rather than catalog_only, keeps it out of root-expansion lists.
    CATALOG_ONLY = False
    PARENT_OPENING_SET_KEY = "legendaryTreasures"
    SUBSET_TYPE = "radiant_collection"
    COUNTS_TOWARD_PARENT_SET_VALUE = True
    COUNTS_TOWARD_PARENT_OPENING = True
    SUPPORTS_OPENING_SIMULATION = False
    USE_MONTE_CARLO_V2 = False
    PULL_MODEL_STATUS = "unsupported"
    PULL_RATE_MAPPING = {}
