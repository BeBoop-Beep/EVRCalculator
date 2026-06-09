from .baseConfig import BaseSetConfig

class SetAstralRadianceConfig(BaseSetConfig):
    SET_NAME = 'Astral Radiance'
    SET_ABBREVIATION = 'ASR'
    SIMULATION_ENGINE = 'slot_schema'
    SLOT_SCHEMA_RUNTIME_ENABLED = True

    SET_ID = 'swsh10'
    RELEASE_DATE = '2022/05/27'
    PRINTED_TOTAL = 189
    TOTAL = 216
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh10/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh10/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/3040/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/3040/cards/?rows=5000&productTypeID=25'
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
            (1 / 5.7)
            + (1 / 7.4)
            + (1 / 34)
            + (1 / 16)
            + (1 / 65)
            + (1 / 110)
            + (1 / 120)
            + (1 / 190)
        ),
        "holo rare": 1 / 5.7,
        "regular v": 1 / 7.4,
        "regular vmax": 1 / 34,
        "regular vstar": 1 / 16,
        "full art": 1 / 65,
        "rainbow rare": 1 / 110,
        "gold rare": 1 / 120,
        "alternate art v": 1 / 190,
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
        "regular vstar": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 189,
                "name_contains": "VSTAR",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "full art": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_range": "167-189",
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
                "card_number_range": "201-211",
                "name_not_contains": "Alternate",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "gold rare": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "212-216",
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
            "Astral Radiance uses high-confidence TCGplayer-family source evidence. "
            "Radiant and Trainer Gallery slot treatment remains explicit and isolated."
        ),
        "blocking_reasons": [],
    }

    ASTRAL_RADIANCE_PULL_RATE_REFERENCE_SOURCES = [
        {
            "source_id": "astral_radiance_tcgplayer_empirical",
            "source_name": "TCGplayer Astral Radiance pull-rate research",
            "source_url": "https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Astral-Radiance-Pull-Rates/10da749f-9c8b-45c0-b80a-dbd86ca5dcde/",
            "source_type": "primary_empirical",
            "source_confidence": "high",
            "discovered_via": "TCGplayer pull-rate publication",
            "notes": "Primary empirical source family for runtime buckets.",
        },
        {
            "source_id": "astral_radiance_thepricedex_cross_reference_2026_05",
            "source_name": "ThePriceDex Astral Radiance pull-rate cross-reference",
            "source_url": "https://www.thepricedex.com/set/swsh10/astral-radiance/pull-rates",
            "source_type": "secondary_index",
            "source_confidence": "medium_low",
            "discovered_via": "ThePriceDex source index",
            "notes": "Cross-reference/index-only source pointer; not SOURCE_DIRECT runtime evidence.",
        },
        {
            "source_id": "astral_radiance_elite_fourum_supplement",
            "source_name": "Elite Fourum Astral Radiance discussion",
            "source_url": "https://www.elitefourum.com/",
            "source_type": "supplementary_discussion",
            "source_confidence": "medium_low",
            "discovered_via": "Elite Fourum supplementary analysis",
            "notes": "Supplementary-only context.",
        },
    ]

    ASTRAL_RADIANCE_PULL_RATE_REFERENCE_BUCKET_EVIDENCE = [
        {
            "source_bucket_label": "V",
            "normalized_bucket": "regular v",
            "odds_display": "1/7.4",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["astral_radiance_tcgplayer_empirical"],
            "caveat": "Direct broad bucket from primary empirical source family.",
        },
        {
            "source_bucket_label": "VMAX",
            "normalized_bucket": "regular vmax",
            "odds_display": "1/34",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["astral_radiance_tcgplayer_empirical"],
            "caveat": "Direct broad bucket from primary empirical source family.",
        },
        {
            "source_bucket_label": "VSTAR",
            "normalized_bucket": "regular vstar",
            "odds_display": "1/16",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["astral_radiance_tcgplayer_empirical"],
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
            "odds_display": "1/65",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["astral_radiance_tcgplayer_empirical"],
            "caveat": "Modeled as broad full-art bucket.",
        },
        {
            "source_bucket_label": "Rainbow Rare",
            "normalized_bucket": "rainbow rare",
            "odds_display": "1/110",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["astral_radiance_tcgplayer_empirical"],
            "caveat": "Direct broad rainbow bucket retained.",
        },
        {
            "source_bucket_label": "Gold Rare",
            "normalized_bucket": "gold rare",
            "odds_display": "1/120",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["astral_radiance_tcgplayer_empirical"],
            "caveat": "Direct broad gold bucket retained.",
        },
        {
            "source_bucket_label": "Alternate Art V",
            "normalized_bucket": "alternate art v",
            "odds_display": "1/190",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["astral_radiance_tcgplayer_empirical"],
            "caveat": "Only directly supported alternate-art child is modeled.",
        },
        {
            "source_bucket_label": "ThePriceDex Rare Holo",
            "normalized_bucket": "holo rare",
            "odds_display": "1/5.7",
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "used_in_runtime": True,
            "source_ids": ["astral_radiance_thepricedex_cross_reference_2026_05"],
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
            "source_ids": ["astral_radiance_thepricedex_cross_reference_2026_05"],
            "caveat": "Index-only row must never be treated as SOURCE_DIRECT.",
        },
    ]
