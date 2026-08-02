from .baseConfig import BaseSetConfig


class SetFirstPartnerCollection2026Config(BaseSetConfig):
    SET_NAME = 'First Partner Collection 2026'
    SET_ABBREVIATION = None

    # SET_ID means Pokemon API set ID; this catalog has no unique API match.
    SET_ID = None
    RELEASE_DATE = None
    PRINTED_TOTAL = None
    TOTAL = None
    SYMBOL_IMAGE_URL = None
    LOGO_IMAGE_URL = None

    # Authoritative TCGplayer catalog identity from the cold-start baseline.
    TCGPLAYER_SET_ID = '24584'
    TCGPLAYER_SET_NAME = 'First Partner Collection 2026'

    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24584/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24584/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # Historical catalog identity added for market/card coverage only.
    # It is NOT an approved pack-simulation product.
    CATALOG_ONLY = True
    SUPPORTS_OPENING_SIMULATION = False
    USE_MONTE_CARLO_V2 = False
    PULL_MODEL_STATUS = "unsupported"
    PULL_RATE_MAPPING = {}
