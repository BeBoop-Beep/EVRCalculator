from .baseConfig import BaseSetConfig

class SetExTrainerKit2PlusleConfig(BaseSetConfig):
    SET_NAME = 'EX Trainer Kit 2 Plusle'
    SET_ABBREVIATION = None

    SET_ID = 'tk2a'
    RELEASE_DATE = '2006/03/01'
    PRINTED_TOTAL = 12
    TOTAL = 12
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/tk2a/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/tk2a/logo.png'

    # No independently attributable TCGplayer card-price source.
    #
    # TCGplayer publishes ONE group for this product ("EX Trainer Kit 2: Plusle &
    # Minun", group 1542) covering both decks. Its rows cannot be deterministically
    # partitioned between the Plusle and Minun canonical sets: both decks are
    # numbered 1/12-12/12 so the number collides, and only 6 of 24 rows carry a
    # "(Plusle)"/"(Minun)" marker (TCGplayer adds it solely to disambiguate
    # identical names, not to label decks). Attaching group 1542 to either child
    # would mislabel combined-market data as one canonical half.
    #
    # The set therefore stays canonical/catalog but leaves the publication-critical
    # daily cohort (CATALOG_ONLY -> ready_for_daily_scrape=False; see migration 058
    # and pokemon_set_lifecycle_flags.is_daily_scrape_ready).
    CATALOG_ONLY = True
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
