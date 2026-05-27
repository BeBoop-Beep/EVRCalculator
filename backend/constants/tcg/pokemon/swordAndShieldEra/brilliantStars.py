from .baseConfig import BaseSetConfig

class SetBrilliantStarsConfig(BaseSetConfig):
    SET_NAME = 'Brilliant Stars'
    SET_ABBREVIATION = 'BRS'
    SIMULATION_ENGINE = 'slot_schema'
    SLOT_SCHEMA_RUNTIME_ENABLED = True

    SET_ID = 'swsh9'
    RELEASE_DATE = '2022/02/25'
    PRINTED_TOTAL = 172
    TOTAL = 186
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh9/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh9/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2948/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2948/cards/?rows=5000&productTypeID=25'
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
            (1 / 3)
            + (1 / 7.2)
            + (1 / 30)
            + (1 / 15)
            + (1 / 62)
            + (1 / 110)
            + (1 / 120)
            + (1 / 180)
        ),
        "holo rare": 1 / 3,
        "regular v": 1 / 7.2,
        "regular vmax": 1 / 30,
        "regular vstar": 1 / 15,
        "full art": 1 / 62,
        "rainbow rare": 1 / 110,
        "gold rare": 1 / 120,
        "alternate art v": 1 / 180,
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
                "card_number_max": 172,
                "name_pattern": "endswith(' V')",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "regular vmax": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 172,
                "name_contains": "VMAX",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "regular vstar": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 172,
                "name_contains": "VSTAR",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "full art": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_range": "153-172",
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
                "card_number_range": "173-183",
                "name_not_contains": "Alternate",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "gold rare": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "184-186",
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
            "Brilliant Stars uses TCGplayer-family evidence with cross-reference support. "
            "Trainer Gallery child rows remain reference-only unless explicitly source-backed for runtime."
        ),
        "blocking_reasons": [],
    }

    BRILLIANT_STARS_PULL_RATE_REFERENCE_SOURCES = [
        {
            "source_id": "brilliant_stars_tcgplayer_empirical",
            "source_name": "TCGplayer Brilliant Stars pull-rate research",
            "source_url": "https://www.tcgplayer.com/",
            "source_type": "primary_empirical",
            "source_confidence": "medium_high",
            "discovered_via": "TCGplayer pull-rate publication and linked derivatives",
            "notes": "Primary empirical source family for runtime-modeled broad buckets.",
        },
        {
            "source_id": "brilliant_stars_thepricedex_cross_reference_2026_05",
            "source_name": "ThePriceDex Brilliant Stars pull-rate cross-reference",
            "source_url": "https://www.thepricedex.com/set/swsh9/brilliant-stars/pull-rates",
            "source_type": "secondary_index",
            "source_confidence": "medium_low",
            "discovered_via": "ThePriceDex source index",
            "notes": "Cross-reference/index-only source pointer; not SOURCE_DIRECT runtime evidence.",
        },
        {
            "source_id": "brilliant_stars_elite_fourum_supplement",
            "source_name": "Elite Fourum Brilliant Stars discussion",
            "source_url": "https://www.elitefourum.com/",
            "source_type": "supplementary_discussion",
            "source_confidence": "medium_low",
            "discovered_via": "Elite Fourum supplementary analysis",
            "notes": "Supplementary-only context; never sole SOURCE_DIRECT authority.",
        },
    ]

    BRILLIANT_STARS_PULL_RATE_REFERENCE_BUCKET_EVIDENCE = [
        {
            "source_bucket_label": "V",
            "normalized_bucket": "regular v",
            "odds_display": "1/7.2",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["brilliant_stars_tcgplayer_empirical"],
            "caveat": "Direct broad bucket from primary empirical source family.",
        },
        {
            "source_bucket_label": "VMAX",
            "normalized_bucket": "regular vmax",
            "odds_display": "1/30",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["brilliant_stars_tcgplayer_empirical"],
            "caveat": "Direct broad bucket from primary empirical source family.",
        },
        {
            "source_bucket_label": "VSTAR",
            "normalized_bucket": "regular vstar",
            "odds_display": "1/15",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["brilliant_stars_tcgplayer_empirical"],
            "caveat": "Direct broad VSTAR row is modeled without unsupported child redistribution.",
        },
        {
            "source_bucket_label": "Full Art",
            "normalized_bucket": "full art",
            "odds_display": "1/62",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["brilliant_stars_tcgplayer_empirical"],
            "caveat": "Modeled as broad full-art bucket.",
        },
        {
            "source_bucket_label": "Alternate Art V",
            "normalized_bucket": "alternate art v",
            "odds_display": "1/180",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["brilliant_stars_tcgplayer_empirical"],
            "caveat": "Only directly supported alternate-art child is modeled.",
        },
        {
            "source_bucket_label": "Rainbow Rare",
            "normalized_bucket": "rainbow rare",
            "odds_display": "1/110",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["brilliant_stars_tcgplayer_empirical"],
            "caveat": "Direct broad rainbow bucket retained.",
        },
        {
            "source_bucket_label": "Gold Rare",
            "normalized_bucket": "gold rare",
            "odds_display": "1/120",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["brilliant_stars_tcgplayer_empirical"],
            "caveat": "Direct broad gold bucket retained.",
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
            "source_bucket_label": "Trainer Gallery",
            "normalized_bucket": "trainer gallery",
            "odds_display": None,
            "source_status": "UNSUPPORTED_SPLIT",
            "source_granularity_status": "UNSUPPORTED_SPLIT",
            "used_in_runtime": False,
            "source_ids": [],
            "caveat": "Trainer Gallery child runtime rows remain unsupported until explicit source-backed split rows are available.",
        },
        {
            "source_bucket_label": "ThePriceDex inferred row",
            "normalized_bucket": "thepricedex inferred",
            "odds_display": None,
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "used_in_runtime": False,
            "source_ids": ["brilliant_stars_thepricedex_cross_reference_2026_05"],
            "caveat": "Index-only row must never be treated as SOURCE_DIRECT.",
        },
    ]
