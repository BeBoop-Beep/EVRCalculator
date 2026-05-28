from .baseConfig import BaseSetConfig

class SetVividVoltageConfig(BaseSetConfig):
    SET_NAME = 'Vivid Voltage'
    SET_ABBREVIATION = 'VIV'
    SIMULATION_ENGINE = 'slot_schema'
    SLOT_SCHEMA_RUNTIME_ENABLED = True

    SET_ID = 'swsh4'
    RELEASE_DATE = '2020/11/13'
    PRINTED_TOTAL = 185
    TOTAL = 203
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2701/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2701/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1.0,
        },
    }

    # Project 17E.2 runtime-limited table (DigitalTQ best-available directional rows).
    # - Amazing Rare is intentionally excluded from runtime buckets pending stronger slot evidence.
    # - rare is residual after modeled non-rare runtime mass.
    RARE_SLOT_PROBABILITY = {
        "rare": 1
        - (
            0.2175
            + 0.1270
            + 0.0429
            + 0.0397
            + 0.0127
            + 0.0111
        ),
        "holo rare": 0.2175,
        "regular v": 0.1270,
        "regular vmax": 0.0429,
        "full art": 0.0397,
        "rainbow rare": 0.0127,
        "gold rare": 0.0111,
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
                "card_number_max": 185,
                "name_pattern": "endswith(' V')",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "regular vmax": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 185,
                "name_contains": "VMAX",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "full art": {
            "source": "rarity + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 185,
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
                "card_number_range": "186-197",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "gold rare": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "198-203",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
    }

    SLOT_SCHEMA_SOURCE_CONFIDENCE = {
        "status": "runtime_limited_provisional_directional",
        "runtime_ready": True,
        "pool_mapping_ready": True,
        "bucket_classification_ready": True,
        "rare_slot_probability_ready": True,
        "reverse_slot_probability_ready": True,
        "source_model": "best_available_directional",
        "source_caveat": (
            "Not official Pokemon pull rates; derived from public empirical/social aggregation. "
            "DigitalTQ Vivid Voltage sample (n=630) is medium-low confidence directional evidence. "
            "ThePriceDex is secondary/index-only and must not be treated as SOURCE_DIRECT. "
            "Amazing Rare remains reference-only and excluded from runtime buckets due to weaker slot-placement confidence. "
            "Vivid Voltage runtime is conservative and excludes Amazing Rare value events from simulated outcomes."
        ),
        "blocking_reasons": [],
    }

    VIVID_VOLTAGE_PULL_RATE_REFERENCE_SOURCES = [
        {
            "source_id": "swsh4_digitaltq_primary_630_2023_11_07",
            "source_name": "DigitalTQ Vivid Voltage Booster Pull Rates",
            "source_url": "https://www.digitaltq.com/vivid-voltage-booster-pull-rates-pokemon-tcg",
            "source_type": "primary_empirical_social",
            "source_confidence": "medium_low",
            "source_author": "Aleph",
            "source_date": "2023-11-07",
            "sample_size": 630,
            "discovered_via": "Direct source audit for swsh4",
            "notes": (
                "Primary best-available directional source for swsh4 runtime-limited modeling. "
                "Community-aggregated and explicitly caveated by publisher as potentially unreliable."
            ),
        },
        {
            "source_id": "swsh4_thepricedex_cross_reference_2026_05",
            "source_name": "ThePriceDex Vivid Voltage pull-rate cross-reference",
            "source_url": "https://www.thepricedex.com/set/swsh4/vivid-voltage/pull-rates",
            "source_type": "secondary_index",
            "source_confidence": "medium_low",
            "discovered_via": "ThePriceDex set pull-rate index",
            "notes": (
                "Cross-reference/index-only source pointer and not sole authority. "
                "ThePriceDex-only inferred or equal-distribution rows must stay SECONDARY_INDEX_ONLY."
            ),
        },
        {
            "source_id": "swsh4_elite_fourum_unusable_direct_2026_05",
            "source_name": "Elite Fourum pull-rate thread (Vivid Voltage section)",
            "source_url": "https://www.elitefourum.com/t/pull-rates-in-sun-moon-sword-shield-sets/25220",
            "source_type": "community_aggregation",
            "source_confidence": "low",
            "discovered_via": "17E source audit",
            "notes": (
                "swsh4 direct table was unavailable/unusable for odds extraction in current review. "
                "Do not treat as SOURCE_DIRECT for swsh4 runtime probability rows."
            ),
        },
    ]

    VIVID_VOLTAGE_PULL_RATE_REFERENCE_BUCKET_EVIDENCE = [
        {
            "source_bucket_label": "Rare Holo V",
            "normalized_bucket": "regular v",
            "odds_display": "1/7.9",
            "source_status": "PROVISIONAL_DIRECTIONAL",
            "source_granularity_status": "PROVISIONAL_DIRECTIONAL",
            "used_in_runtime": True,
            "source_ids": ["swsh4_digitaltq_primary_630_2023_11_07"],
            "caveat": "DigitalTQ directional row mapped to broad regular-v runtime bucket.",
        },
        {
            "source_bucket_label": "Rare Holo VMAX",
            "normalized_bucket": "regular vmax",
            "odds_display": "1/23.3",
            "source_status": "PROVISIONAL_DIRECTIONAL",
            "source_granularity_status": "PROVISIONAL_DIRECTIONAL",
            "used_in_runtime": True,
            "source_ids": ["swsh4_digitaltq_primary_630_2023_11_07"],
            "caveat": "DigitalTQ directional row retained without unsupported child split.",
        },
        {
            "source_bucket_label": "Ultra Rare",
            "normalized_bucket": "full art",
            "odds_display": "1/25.2",
            "source_status": "PROVISIONAL_DIRECTIONAL",
            "source_granularity_status": "PROVISIONAL_DIRECTIONAL",
            "used_in_runtime": True,
            "source_ids": ["swsh4_digitaltq_primary_630_2023_11_07"],
            "caveat": "Directional mapping to full-art runtime policy from Ultra Rare row.",
        },
        {
            "source_bucket_label": "Rare Rainbow",
            "normalized_bucket": "rainbow rare",
            "odds_display": "1/78.7",
            "source_status": "PROVISIONAL_DIRECTIONAL",
            "source_granularity_status": "PROVISIONAL_DIRECTIONAL",
            "used_in_runtime": True,
            "source_ids": ["swsh4_digitaltq_primary_630_2023_11_07"],
            "caveat": "Directional rainbow row used in conservative runtime-limited table.",
        },
        {
            "source_bucket_label": "Secret Rare Holo",
            "normalized_bucket": "gold rare",
            "odds_display": "1/90.1",
            "source_status": "PROVISIONAL_DIRECTIONAL",
            "source_granularity_status": "PROVISIONAL_DIRECTIONAL",
            "used_in_runtime": True,
            "source_ids": ["swsh4_digitaltq_primary_630_2023_11_07"],
            "caveat": "Directional secret row mapped to gold-rare runtime bucket policy.",
        },
        {
            "source_bucket_label": "Rare residual",
            "normalized_bucket": "rare",
            "odds_display": "residual",
            "source_status": "SOURCE_DERIVED_RESIDUAL",
            "source_granularity_status": "SOURCE_DERIVED_RESIDUAL",
            "used_in_runtime": True,
            "source_ids": [],
            "caveat": "Residual after explicit modeled runtime mass excluding Amazing Rare.",
        },
        {
            "source_bucket_label": "Rare Holo",
            "normalized_bucket": "holo rare",
            "odds_display": "1/4.6",
            "source_status": "PROVISIONAL_DIRECTIONAL",
            "source_granularity_status": "PROVISIONAL_DIRECTIONAL",
            "used_in_runtime": True,
            "source_ids": ["swsh4_digitaltq_primary_630_2023_11_07"],
            "caveat": "Directional holo-rare row retained as explicit runtime outcome.",
        },
        {
            "source_bucket_label": "Amazing Rare",
            "normalized_bucket": "amazing rare",
            "odds_display": "1/17.5",
            "source_status": "PROVISIONAL_DIRECTIONAL",
            "source_granularity_status": "PROVISIONAL_DIRECTIONAL",
            "used_in_runtime": False,
            "source_ids": ["swsh4_digitaltq_primary_630_2023_11_07"],
            "caveat": (
                "Explicit frequency exists, but slot placement and confidence are insufficient for safe runtime modeling. "
                "Remain reference-only in 17E.2."
            ),
        },
        {
            "source_bucket_label": "ThePriceDex pull-rate index row",
            "normalized_bucket": "thepricedex modeled row",
            "odds_display": None,
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "used_in_runtime": False,
            "source_ids": ["swsh4_thepricedex_cross_reference_2026_05"],
            "caveat": "Index-only row; never promoted to SOURCE_DIRECT runtime evidence.",
        },
        {
            "source_bucket_label": "Trainer Gallery",
            "normalized_bucket": "trainer gallery",
            "odds_display": None,
            "source_status": "MISSING_SOURCE",
            "source_granularity_status": "MISSING_SOURCE",
            "used_in_runtime": False,
            "source_ids": [],
            "caveat": "Not a swsh4 runtime bucket in this project phase.",
        },
        {
            "source_bucket_label": "Radiant / VSTAR",
            "normalized_bucket": "radiant_or_vstar",
            "odds_display": None,
            "source_status": "MISSING_SOURCE",
            "source_granularity_status": "MISSING_SOURCE",
            "used_in_runtime": False,
            "source_ids": [],
            "caveat": "swsh4 predates Radiant and VSTAR runtime buckets.",
        },
    ]
