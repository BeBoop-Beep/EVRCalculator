from .baseConfig import BaseSetConfig


class SetMe30thCelebrationConfig(BaseSetConfig):
    SET_NAME = 'ME: 30th Celebration'
    SET_ABBREVIATION = None
    # Official Pokemon metadata identifies 30th Celebration as part of the
    # Mega Evolution Series. Keep the historical config path stable while
    # syncing the public catalog to the correct era.
    ERA_CANONICAL_KEY = "megaEvolutionEra"

    # SET_ID means Pokemon API set ID; this catalog still has no unique API match.
    SET_ID = None
    RELEASE_DATE = '2026-09-16'
    PRINTED_TOTAL = None
    TOTAL = None
    SYMBOL_IMAGE_URL = None
    LOGO_IMAGE_URL = None

    # Authoritative TCGplayer catalog identity from the cold-start baseline.
    TCGPLAYER_SET_ID = '24722'
    TCGPLAYER_SET_NAME = 'ME: 30th Celebration'

    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24722/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24722/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # Normal root-set lifecycle, matching older root/subset families such as
    # Celebrations + Classic Collection. The set is scrape/market eligible now;
    # opening simulation remains gated until a validated pull model is approved.
    CATALOG_ONLY = False
    SUPPORTS_OPENING_SIMULATION = False
    USE_MONTE_CARLO_V2 = False
    PULL_MODEL_STATUS = "pending"
    PULL_RATE_MAPPING = {}
