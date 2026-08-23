from .baseConfig import BaseSetConfig


class SetExpeditionConfig(BaseSetConfig):
    SET_NAME = 'Expedition'
    SET_ABBREVIATION = None

    # SET_ID means Pokemon API set ID; this catalog has no unique API match.
    SET_ID = None
    RELEASE_DATE = None
    PRINTED_TOTAL = None
    TOTAL = None
    SYMBOL_IMAGE_URL = None
    LOGO_IMAGE_URL = None

    # Retired duplicate of `expeditionBaseSet` (ecard1).
    #
    # This cold-start catalog row and `expeditionBaseSet` both modelled the same
    # real-world set. `expeditionBaseSet` is the canonical owner: it holds the
    # ecard1 identity, the daily-cohort slot and the public daily history, and it
    # now owns TCGplayer group 1375 plus the authoritative 165-card roster that
    # was consolidated out of this row.
    #
    # The source URLs are cleared so one provider group has exactly one canonical
    # owner. Re-adding them here would recreate the duplicate-source defect that
    # blocked batch 26.
    TCGPLAYER_SET_NAME = 'Expedition'

    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # Historical catalog identity added for market/card coverage only.
    # It is NOT an approved pack-simulation product.
    CATALOG_ONLY = True
    SUPPORTS_OPENING_SIMULATION = False
    USE_MONTE_CARLO_V2 = False
    PULL_MODEL_STATUS = "unsupported"
    PULL_RATE_MAPPING = {}
