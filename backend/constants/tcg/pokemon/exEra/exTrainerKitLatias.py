from .baseConfig import BaseSetConfig

class SetExTrainerKitLatiasConfig(BaseSetConfig):
    SET_NAME = 'EX Trainer Kit Latias'
    SET_ABBREVIATION = None

    SET_ID = 'tk1a'
    RELEASE_DATE = '2004/06/01'
    PRINTED_TOTAL = 10
    TOTAL = 10
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/tk1a/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/tk1a/logo.png'

    # No independently attributable TCGplayer card-price source.
    #
    # TCGplayer publishes ONE group for this product ("EX Trainer Kit 1: Latias &
    # Latios", group 1543) covering both decks. Its rows cannot be deterministically
    # partitioned between the Latias and Latios canonical sets: both decks are
    # numbered 1/10-10/10 so the number collides, and only 4 of 20 rows carry a
    # "(Latias)"/"(Latios)" marker (TCGplayer adds it solely to disambiguate
    # identical names, not to label decks). Attaching group 1543 to either child
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
