from .baseConfig import BaseSetConfig

class SetSilverTempestConfig(BaseSetConfig):
    SET_NAME = 'Silver Tempest'
    SET_ABBREVIATION = 'SIT'
    SIMULATION_ENGINE = 'slot_schema'
    SLOT_SCHEMA_RUNTIME_ENABLED = True

    SET_ID = 'swsh12'
    RELEASE_DATE = '2022/11/11'
    PRINTED_TOTAL = 195
    TOTAL = 215
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh12/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh12/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/3170/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/3170/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1.0,
        },
    }

    RARE_SLOT_PROBABILITY = {
        "rare": 1
        - (
            (1 / 5.6)
            + (1 / 7.8)
            + (1 / 35)
            + (1 / 16)
            + (1 / 72)
            + (1 / 118)
            + (1 / 130)
            + (1 / 210)
        ),
        "holo rare": 1 / 5.6,
        "regular v": 1 / 7.8,
        "regular vmax": 1 / 35,
        "regular vstar": 1 / 16,
        "full art": 1 / 72,
        "rainbow rare": 1 / 118,
        "gold rare": 1 / 130,
        "alternate art v": 1 / 210,
    }

    SLOT_SCHEMA_OUTCOME_POOL_MAPPING = {
        "rare": {
            "source": "rarity + printing_type",
            "card_filter": {"rarity": "Rare"},
            "variant_filter": {"printing_type": "non-holo"},
            "include_reverse_variants": False,
        },
        "holo rare": {
            "source": "rarity + printing_type",
            "card_filter": {"rarity": "Holo Rare"},
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "regular v": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 195,
                "name_pattern": "endswith(' V')",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "regular vmax": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 195,
                "name_contains": "VMAX",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "regular vstar": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 195,
                "name_contains": "VSTAR",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "full art": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_range": "176-195",
                "name_not_contains": "Alternate",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "alternate art v": {
            "source": "rarity + name",
            "card_filter": {
                "rarity": "Ultra Rare",
                "name_contains": "(Alternate Full Art)",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "rainbow rare": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "200-209",
                "name_not_contains": "Alternate",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "gold rare": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "210-215",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
    }

    SLOT_SCHEMA_SOURCE_CONFIDENCE = {
        "status": "runtime_candidate_best_available_empirical",
        "runtime_ready": True,
        "pool_mapping_ready": True,
        "bucket_classification_ready": True,
        "rare_slot_probability_ready": True,
        "reverse_slot_probability_ready": True,
        "source_model": "best_available_empirical",
        "source_caveat": (
            "Not official Pokemon pull rates; derived from public empirical samples. "
            "Silver Tempest uses high-confidence TCGplayer-family source evidence. "
            "Radiant and Trainer Gallery slot treatment remains explicit and isolated."
        ),
        "blocking_reasons": [],
    }

    SILVER_TEMPEST_PULL_RATE_REFERENCE_SOURCES = [
        {
            "source_id": "silver_tempest_tcgplayer_empirical",
            "source_name": "TCGplayer Silver Tempest pull-rate research",
            "source_url": "https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Silver-Tempest-Pull-Rates/6490d591-e582-4930-8446-00e190876d30/",
            "source_type": "primary_empirical",
            "source_confidence": "high",
            "discovered_via": "TCGplayer pull-rate publication",
            "notes": "Primary empirical source family for runtime buckets.",
        },
        {
            "source_id": "silver_tempest_thepricedex_cross_reference_2026_05",
            "source_name": "ThePriceDex Silver Tempest pull-rate cross-reference",
            "source_url": "https://www.thepricedex.com/set/swsh12/silver-tempest/pull-rates",
            "source_type": "secondary_index",
            "source_confidence": "medium_low",
            "discovered_via": "ThePriceDex source index",
            "notes": "Cross-reference/index-only source pointer; not SOURCE_DIRECT runtime evidence.",
        },
        {
            "source_id": "silver_tempest_elite_fourum_supplement",
            "source_name": "Elite Fourum Silver Tempest discussion",
            "source_url": "https://www.elitefourum.com/",
            "source_type": "supplementary_discussion",
            "source_confidence": "medium_low",
            "discovered_via": "Elite Fourum supplementary analysis",
            "notes": "Supplementary-only context.",
        },
    ]

    SILVER_TEMPEST_PULL_RATE_REFERENCE_BUCKET_EVIDENCE = [
        {
            "source_bucket_label": "V",
            "normalized_bucket": "regular v",
            "odds_display": "1/7.8",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["silver_tempest_tcgplayer_empirical"],
            "caveat": "Direct broad bucket from primary empirical source family.",
        },
        {
            "source_bucket_label": "VMAX",
            "normalized_bucket": "regular vmax",
            "odds_display": "1/35",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["silver_tempest_tcgplayer_empirical"],
            "caveat": "Direct broad bucket from primary empirical source family.",
        },
        {
            "source_bucket_label": "VSTAR",
            "normalized_bucket": "regular vstar",
            "odds_display": "1/16",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["silver_tempest_tcgplayer_empirical"],
            "caveat": "Direct broad VSTAR row retained.",
        },
        {
            "source_bucket_label": "Radiant Rare",
            "normalized_bucket": "radiant rare",
            "odds_display": None,
            "source_status": "UNSUPPORTED_SPLIT",
            "source_granularity_status": "UNSUPPORTED_SPLIT",
            "used_in_runtime": False,
            "source_ids": [],
            "caveat": "Radiant rows remain reference-only until runtime-safe local classification keys are available.",
        },
        {
            "source_bucket_label": "Trainer Gallery (combined)",
            "normalized_bucket": "trainer gallery",
            "odds_display": None,
            "source_status": "UNSUPPORTED_SPLIT",
            "source_granularity_status": "UNSUPPORTED_SPLIT",
            "used_in_runtime": False,
            "source_ids": [],
            "caveat": "Trainer Gallery rows remain reference-only until runtime-safe local classification keys are available.",
        },
        {
            "source_bucket_label": "Full Art",
            "normalized_bucket": "full art",
            "odds_display": "1/72",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["silver_tempest_tcgplayer_empirical"],
            "caveat": "Modeled as broad full-art bucket.",
        },
        {
            "source_bucket_label": "Rainbow Rare",
            "normalized_bucket": "rainbow rare",
            "odds_display": "1/118",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["silver_tempest_tcgplayer_empirical"],
            "caveat": "Direct broad rainbow bucket retained.",
        },
        {
            "source_bucket_label": "Gold Rare",
            "normalized_bucket": "gold rare",
            "odds_display": "1/130",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["silver_tempest_tcgplayer_empirical"],
            "caveat": "Direct broad gold bucket retained.",
        },
        {
            "source_bucket_label": "Alternate Art V",
            "normalized_bucket": "alternate art v",
            "odds_display": "1/210",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["silver_tempest_tcgplayer_empirical"],
            "caveat": "Only directly supported alternate-art child is modeled.",
        },
        {
            "source_bucket_label": "ThePriceDex Rare Holo",
            "normalized_bucket": "holo rare",
            "odds_display": "1/5.6",
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "used_in_runtime": True,
            "source_ids": ["silver_tempest_thepricedex_cross_reference_2026_05"],
            "caveat": "Best-available ThePriceDex cross-reference used for runtime; not SOURCE_DIRECT evidence.",
        },
        {
            "source_bucket_label": "Rare residual",
            "normalized_bucket": "rare",
            "odds_display": "residual",
            "source_status": "SOURCE_DERIVED_RESIDUAL",
            "source_granularity_status": "SOURCE_DERIVED_RESIDUAL",
            "used_in_runtime": True,
            "source_ids": [],
            "caveat": "Residual bucket after explicit non-rare modeled mass.",
        },
        {
            "source_bucket_label": "ThePriceDex inferred row",
            "normalized_bucket": "thepricedex inferred",
            "odds_display": None,
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "used_in_runtime": False,
            "source_ids": ["silver_tempest_thepricedex_cross_reference_2026_05"],
            "caveat": "Index-only row must never be treated as SOURCE_DIRECT.",
        },
    ]
