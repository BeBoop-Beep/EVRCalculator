from .baseConfig import BaseSetConfig


class SetMe06DeltaReignConfig(BaseSetConfig):
    SET_NAME = 'ME06: Delta Reign'
    SET_ABBREVIATION = None

    # Provider-only catalog identity. Pokemon.com confirms this is a
    # Mega Evolution Series expansion releasing 2026-11-06; no Pokemon TCG API
    # identity is claimed until that source exposes one.
    SET_ID = None
    RELEASE_DATE = '2026-11-06'
    PRINTED_TOTAL = None
    TOTAL = None
    SYMBOL_IMAGE_URL = None
    LOGO_IMAGE_URL = None

    TCGPLAYER_SET_ID = '24831'
    TCGPLAYER_SET_NAME = 'ME06: Delta Reign'

    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24831/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24831/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    CATALOG_ONLY = True
    SUPPORTS_OPENING_SIMULATION = False
    USE_MONTE_CARLO_V2 = False
    PULL_MODEL_STATUS = "unsupported"
    PULL_RATE_MAPPING = {}
