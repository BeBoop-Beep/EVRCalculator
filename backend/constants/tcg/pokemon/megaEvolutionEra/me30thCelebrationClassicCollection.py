from .baseConfig import BaseSetConfig


class SetMe30thCelebrationClassicCollectionConfig(BaseSetConfig):
    PARENT_OPENING_SET_KEY = "me30thCelebration"
    IS_SUBSET = True
    SUBSET_TYPE = "classic_collection"
    COUNTS_TOWARD_PARENT_SET_VALUE = True
    COUNTS_TOWARD_PARENT_OPENING = True

    SET_NAME = 'ME: 30th Celebration Classic Collection'
    SET_ABBREVIATION = None

    # Official Pokemon material identifies Classic Collection as a pack-pulled
    # subset of 30th Celebration. Match the established Celebrations/Classic
    # Collection contract: scrape it independently, but roll its cards into the
    # parent set-value/opening universe rather than exposing it as a root set.
    # Verified direct subset identity in the live Pokemon TCG API catalog.
    SET_ID = 'me55c'
    RELEASE_DATE = '2026-09-16'
    PRINTED_TOTAL = 30
    TOTAL = 30
    SYMBOL_IMAGE_URL = 'https://images.scrydex.com/pokemon/me55c-symbol/symbol'
    LOGO_IMAGE_URL = 'https://images.scrydex.com/pokemon/me55c-logo/logo'

    TCGPLAYER_SET_ID = '24837'
    TCGPLAYER_SET_NAME = 'ME: 30th Celebration Classic Collection'

    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24837/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24837/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    CATALOG_ONLY = False
    SUPPORTS_OPENING_SIMULATION = False
    USE_MONTE_CARLO_V2 = False
    PULL_MODEL_STATUS = "unsupported"
    PULL_RATE_MAPPING = {}
