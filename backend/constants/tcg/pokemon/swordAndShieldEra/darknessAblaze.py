from .baseConfig import BaseSetConfig

class SetDarknessAblazeConfig(BaseSetConfig):
    SET_NAME = 'Darkness Ablaze'
    SET_ABBREVIATION = 'DAA'
    SIMULATION_ENGINE = 'slot_schema'
    SLOT_SCHEMA_RUNTIME_ENABLED = True

    SET_ID = 'swsh3'
    RELEASE_DATE = '2020/08/14'
    PRINTED_TOTAL = 189
    TOTAL = 201
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2675/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2675/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1.0,
        },
    }

    # Project 17D.2 runtime seed table (Elite Fourum best-available empirical rows).
    # - rare and holo rare remain explicit residual/derived outcomes.
    # - no Amazing Rare, Trainer Gallery, Radiant, or VSTAR runtime buckets in swsh3.
    RARE_SLOT_PROBABILITY = {
        "rare": 1
        - (
            (1 / 5.9)
            + (1 / 7.95)
            + (1 / 25.98)
            + (1 / 25.98)
            + (1 / 84.00)
            + (1 / 114.55)
        ),
        "holo rare": 1 / 5.9,
        "regular v": 1 / 7.95,
        "regular vmax": 1 / 25.98,
        "full art": 1 / 25.98,
        "rainbow rare": 1 / 84.00,
        "gold rare": 1 / 114.55,
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
                "card_number_max": 189,
                "name_pattern": "endswith(' V')",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "regular vmax": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 189,
                "name_contains": "VMAX",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "full art": {
            "source": "rarity + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 189,
                "name_contains": "(Full Art)",
                "name_not_contains": "Alternate",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "rainbow rare": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "190-197",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "gold rare": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "198-201",
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
            "ThePriceDex is cross-reference/index-only metadata and must not be treated as SOURCE_DIRECT. "
            "swsh3 keeps broad buckets only; unsupported specialty rows remain reference-only."
        ),
        "blocking_reasons": [],
    }

    DARKNESS_ABLAZE_PULL_RATE_REFERENCE_SOURCES = [
        {
            "source_id": "swsh3_elite_fourum_primary_5040_2020_09_16",
            "source_name": "Elite Fourum pull-rate thread (Darkness Ablaze)",
            "source_url": "https://www.elitefourum.com/t/pull-rates-in-sun-moon-sword-shield-sets/25220",
            "source_type": "community_aggregation",
            "source_confidence": "high",
            "discovered_via": "Elite Fourum user-maintained pack-study table",
            "notes": (
                "Primary community empirical source for swsh3 with 5,040 packs in the 2020-09-16 dataset. "
                "Sample-based evidence and not official Pokemon-published odds."
            ),
        },
        {
            "source_id": "swsh3_thepricedex_cross_reference_2026_05",
            "source_name": "ThePriceDex Darkness Ablaze pull-rate cross-reference",
            "source_url": "https://www.thepricedex.com/set/swsh3/darkness-ablaze/pull-rates",
            "source_type": "secondary_index",
            "source_confidence": "medium_low",
            "discovered_via": "ThePriceDex set pull-rate index",
            "notes": (
                "Cross-reference/index-only source pointer and not sole authority. "
                "ThePriceDex-only inferred or equal-distribution rows must stay SECONDARY_INDEX_ONLY."
            ),
        },
        {
            "source_id": "swsh3_elite_fourum_rarity_guide_supplement",
            "source_name": "Elite Fourum English rarity guide discussion",
            "source_url": "https://www.elitefourum.com/t/the-english-pokemon-card-rarity-guide/39762/158",
            "source_type": "supplementary_discussion",
            "source_confidence": "medium_low",
            "discovered_via": "Elite Fourum rarity-guide supplementary linkage",
            "notes": "Supplementary directional context only; not sole SOURCE_DIRECT authority.",
        },
    ]

    DARKNESS_ABLAZE_PULL_RATE_REFERENCE_BUCKET_EVIDENCE = [
        {
            "source_bucket_label": "Rare Holo V",
            "normalized_bucket": "regular v",
            "odds_display": "1/7.95",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["swsh3_elite_fourum_primary_5040_2020_09_16"],
            "caveat": "Direct broad row from Elite Fourum pack study.",
        },
        {
            "source_bucket_label": "Rare Holo VMAX",
            "normalized_bucket": "regular vmax",
            "odds_display": "1/25.98",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["swsh3_elite_fourum_primary_5040_2020_09_16"],
            "caveat": "Direct broad row retained without unsupported child split.",
        },
        {
            "source_bucket_label": "Ultra Rare",
            "normalized_bucket": "full art",
            "odds_display": "1/25.98",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["swsh3_elite_fourum_primary_5040_2020_09_16"],
            "caveat": "Mapped to full art runtime bucket per local taxonomy policy.",
        },
        {
            "source_bucket_label": "Rainbow Rare",
            "normalized_bucket": "rainbow rare",
            "odds_display": "1/84.00",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["swsh3_elite_fourum_primary_5040_2020_09_16"],
            "caveat": "Direct broad rainbow row retained.",
        },
        {
            "source_bucket_label": "Secret Rare",
            "normalized_bucket": "gold rare",
            "odds_display": "1/114.55",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["swsh3_elite_fourum_primary_5040_2020_09_16"],
            "caveat": "Direct broad secret row mapped to gold-rare runtime bucket policy.",
        },
        {
            "source_bucket_label": "Rare residual",
            "normalized_bucket": "rare",
            "odds_display": "residual",
            "source_status": "SOURCE_DERIVED_RESIDUAL",
            "source_granularity_status": "SOURCE_DERIVED_RESIDUAL",
            "used_in_runtime": True,
            "source_ids": [],
            "caveat": "Residual after explicit non-rare modeled mass.",
        },
        {
            "source_bucket_label": "ThePriceDex Rare Holo",
            "normalized_bucket": "holo rare",
            "odds_display": "1/5.9",
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "used_in_runtime": True,
            "source_ids": ["swsh3_thepricedex_cross_reference_2026_05"],
            "caveat": "Best-available ThePriceDex cross-reference used for runtime; not SOURCE_DIRECT evidence.",
        },
        {
            "source_bucket_label": "ThePriceDex modeled/equal-distribution row",
            "normalized_bucket": "thepricedex modeled row",
            "odds_display": None,
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "used_in_runtime": False,
            "source_ids": ["swsh3_thepricedex_cross_reference_2026_05"],
            "caveat": "Index-only row; never promoted to SOURCE_DIRECT runtime evidence.",
        },
        {
            "source_bucket_label": "Amazing Rare",
            "normalized_bucket": "amazing rare",
            "odds_display": None,
            "source_status": "MISSING_SOURCE",
            "source_granularity_status": "MISSING_SOURCE",
            "used_in_runtime": False,
            "source_ids": [],
            "caveat": "Not a swsh3 runtime bucket.",
        },
        {
            "source_bucket_label": "Trainer Gallery",
            "normalized_bucket": "trainer gallery",
            "odds_display": None,
            "source_status": "MISSING_SOURCE",
            "source_granularity_status": "MISSING_SOURCE",
            "used_in_runtime": False,
            "source_ids": [],
            "caveat": "swsh3 predates Trainer Gallery runtime modeling.",
        },
        {
            "source_bucket_label": "Radiant / VSTAR",
            "normalized_bucket": "radiant_or_vstar",
            "odds_display": None,
            "source_status": "MISSING_SOURCE",
            "source_granularity_status": "MISSING_SOURCE",
            "used_in_runtime": False,
            "source_ids": [],
            "caveat": "swsh3 predates Radiant and VSTAR runtime buckets.",
        },
    ]
