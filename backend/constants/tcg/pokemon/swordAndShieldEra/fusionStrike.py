from .baseConfig import BaseSetConfig

class SetFusionStrikeConfig(BaseSetConfig):
    SET_NAME = 'Fusion Strike'
    SET_ABBREVIATION = 'FST'
    SIMULATION_ENGINE = 'slot_schema'
    SLOT_SCHEMA_RUNTIME_ENABLED = True

    SET_ID = 'swsh8'
    RELEASE_DATE = '2021/11/12'
    PRINTED_TOTAL = 264
    TOTAL = 284
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh8/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh8/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2906/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2906/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}

    # Reverse slot remains the safe standard SWSH assumption scaffold:
    # one reverse slot with regular reverse at full mass.
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1.0,
        },
    }

    # Locked Project 17B.3d runtime assumptions for swsh8.
    # Primary source rows are from Reddit/TheGameCapital (3024 packs).
    # - Hyper is treated as rainbow rare taxonomy.
    # - Gold is treated as gold rare taxonomy.
    # - holo rare uses best-available ThePriceDex cross-reference (secondary-index only).
    # - rare is residual mass after explicit buckets.
    RARE_SLOT_PROBABILITY = {
        "rare": 1
        - (
            (1 / 5.6)
            + (1 / 7.8)
            + (1 / 28)
            + (1 / 66)
            + (1 / 72)
            + (1 / 126)
            + (1 / 116)
            + (1 / 137)
            + (1 / 275)
        ),
        "holo rare": 1 / 5.6,
        "regular v": 1 / 7.8,
        "regular vmax": 1 / 28,
        "full art pokemon": 1 / 66,
        "full art supporter": 1 / 72,
        "alternate art v": 1 / 137,
        "alternate art vmax": 1 / 275,
        "rainbow rare": 1 / 126,
        "gold rare": 1 / 116,
    }

    # Runtime slot-schema pool contract.
    # Filters are mutually exclusive to avoid overlap and double counting.
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
                "card_number_max": 244,
                "name_pattern": "endswith(' V')",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "regular vmax": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 244,
                "name_contains": "VMAX",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "full art pokemon": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_range": "245-264",
                "name_contains": " V",
                "name_not_contains": "Alternate",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "full art supporter": {
            "source": "rarity + exact card_number block",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_range": "258-264",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "alternate art v": {
            "source": "rarity + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "name_contains": "(Alternate Full Art)",
                "name_contains_all": [" V"],
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "alternate art vmax": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "270-271",
                "name_contains": "Alternate Art Secret",
                "name_contains_all": ["VMAX"],
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "rainbow rare": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "272-278",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "gold rare": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "279-284",
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
            "ThePriceDex is cross-reference/index-only for this runtime model. "
            "Alt-art rows have lower confidence due to Reddit vs TCGplayer sample disagreement."
        ),
        "blocking_reasons": [],
    }

    # Project 17B.2: Source-backed pull-rate reference metadata only.
    # Runtime probabilities remain unchanged and are intentionally not inferred
    # from these rows in this phase.
    FUSION_STRIKE_PULL_RATE_REFERENCE_SOURCES = [
        {
            "source_id": "fusion_strike_reddit_3024_chart_2021_11",
            "source_name": "Reddit / TheGameCapital Fusion Strike 3024-pack chart",
            "source_url": "https://www.reddit.com/r/PokemonTCG/comments/qnvvvo/fusion_strikes_pull_rate_data_3000_packs/",
            "source_type": "community_aggregation",
            "source_confidence": "medium",
            "discovered_via": "Reddit, r/PokemonTCG, xdomx21, TheGameCapital, 3024 packs, 84 booster boxes",
            "notes": (
                "Community-posted chart for Fusion Strike based on 3024 packs / 84 booster boxes, "
                "attributed in-image to TheGameCapital on YouTube. Image: https://i.redd.it/nhfp4vk6pxx71.png. "
                "Sample-based evidence, not official Pokemon-published odds."
            ),
        },
        {
            "source_id": "fusion_strike_tcgplayer_instagram_4000plus_2021_11",
            "source_name": "TCGplayer Fusion Strike 4000+ pack pull-rate post",
            "source_url": "https://www.instagram.com/p/CWMOH29vLzE/",
            "source_type": "primary_empirical_social",
            "source_confidence": "medium_high",
            "discovered_via": "TCGplayer, tcgplayer_com, Instagram, 4000+ packs, Fusion Strike pull rates",
            "notes": (
                "TCGplayer social post states over 4000 Fusion Strike packs were opened and provides "
                "visible row-level pull-rate odds. Social media artifact with no long-form methods page "
                "found. Sample-based evidence, not official Pokemon-published odds."
            ),
        },
        {
            "source_id": "fusion_strike_thepricedex_cross_reference_2026_05",
            "source_name": "ThePriceDex Fusion Strike pull-rate cross-reference",
            "source_url": "https://www.thepricedex.com/set/swsh8/fusion-strike/pull-rates",
            "source_type": "secondary_index",
            "source_confidence": "medium_low",
            "discovered_via": "ThePriceDex, pull-rate cross-reference, Fusion Strike pull rates",
            "notes": (
                "Used as a pull-rate cross-reference and source/reference index only. ThePriceDex discloses "
                "mixed methodology including community data, supplementary analysis, estimated reverse rates, "
                "and equal-within-rarity assumptions. Do not treat ThePriceDex-only inferred rows as source-direct."
            ),
        },
    ]

    FUSION_STRIKE_PULL_RATE_REFERENCE_BUCKET_EVIDENCE = [
        {
            "source_bucket_label": "V",
            "normalized_bucket": "v",
            "odds_display": "1/7.8",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_reddit_3024_chart_2021_11"],
            "caveat": "Community sample; sample-based evidence and not official Pokemon odds.",
        },
        {
            "source_bucket_label": "VMAX",
            "normalized_bucket": "vmax",
            "odds_display": "1/28",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_reddit_3024_chart_2021_11"],
            "caveat": "Cross-source taxonomy is not perfectly identical.",
        },
        {
            "source_bucket_label": "Full Art Pokemon",
            "normalized_bucket": "full art pokemon",
            "odds_display": "1/66",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_reddit_3024_chart_2021_11"],
            "caveat": "Bucket naming differs across sources.",
        },
        {
            "source_bucket_label": "Full Art Supporter",
            "normalized_bucket": "full art supporter",
            "odds_display": "1/72",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_reddit_3024_chart_2021_11"],
            "caveat": "Social/community sample variance is expected.",
        },
        {
            "source_bucket_label": "Hyper",
            "normalized_bucket": "hyper",
            "odds_display": "1/126",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_reddit_3024_chart_2021_11"],
            "caveat": "Hyper and Rainbow naming are treated as equivalent taxonomy labels.",
        },
        {
            "source_bucket_label": "Gold",
            "normalized_bucket": "gold",
            "odds_display": "1/116",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_reddit_3024_chart_2021_11"],
            "caveat": "Minor sample variance versus TCGplayer is expected.",
        },
        {
            "source_bucket_label": "Alt V",
            "normalized_bucket": "alt v",
            "odds_display": "1/137",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_reddit_3024_chart_2021_11"],
            "caveat": "Moderate contradiction versus TCGplayer sample; keep confidence conservative.",
        },
        {
            "source_bucket_label": "Alt VMAX",
            "normalized_bucket": "alt vmax",
            "odds_display": "1/275",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_reddit_3024_chart_2021_11"],
            "caveat": "Moderate contradiction versus TCGplayer sample; keep confidence conservative.",
        },
        {
            "source_bucket_label": "Alt V or VMAX combined",
            "normalized_bucket": "alt v or vmax combined",
            "odds_display": "1/92",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_reddit_3024_chart_2021_11"],
            "caveat": "Combined bucket should not force unsupported child redistribution.",
        },
        {
            "source_bucket_label": "Hits per 36 packs",
            "normalized_bucket": "hits per 36 packs",
            "odds_display": "7.92 per 36 packs",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_reddit_3024_chart_2021_11"],
            "caveat": "Community-box sample statistic; not official Pokemon odds.",
        },
        {
            "source_bucket_label": "Alt-Art VMAX",
            "normalized_bucket": "alt art vmax",
            "odds_display": "1/332",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_tcgplayer_instagram_4000plus_2021_11"],
            "caveat": "Social media sample artifact.",
        },
        {
            "source_bucket_label": "Alt-Art V",
            "normalized_bucket": "alt art v",
            "odds_display": "1/180",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_tcgplayer_instagram_4000plus_2021_11"],
            "caveat": "Social media sample artifact.",
        },
        {
            "source_bucket_label": "Golden Rare",
            "normalized_bucket": "golden rare",
            "odds_display": "1/120",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_tcgplayer_instagram_4000plus_2021_11"],
            "caveat": "Social media sample artifact.",
        },
        {
            "source_bucket_label": "Rainbow Rare",
            "normalized_bucket": "rainbow rare",
            "odds_display": "1/127",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_tcgplayer_instagram_4000plus_2021_11"],
            "caveat": "Social media sample artifact.",
        },
        {
            "source_bucket_label": "Full-Art Trainer",
            "normalized_bucket": "full art trainer",
            "odds_display": "1/64",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_tcgplayer_instagram_4000plus_2021_11"],
            "caveat": "Social media sample artifact.",
        },
        {
            "source_bucket_label": "Full-Art V",
            "normalized_bucket": "full art v",
            "odds_display": "1/58",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_tcgplayer_instagram_4000plus_2021_11"],
            "caveat": "Social media sample artifact.",
        },
        {
            "source_bucket_label": "Holo VMAX",
            "normalized_bucket": "holo vmax",
            "odds_display": "1/30",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_tcgplayer_instagram_4000plus_2021_11"],
            "caveat": "Social media sample artifact.",
        },
        {
            "source_bucket_label": "Hit Rate, Ultra Rare or better",
            "normalized_bucket": "hit rate ultra rare or better",
            "odds_display": "1/5",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "source_ids": ["fusion_strike_tcgplayer_instagram_4000plus_2021_11"],
            "caveat": "Social media sample artifact.",
        },
        {
            "source_bucket_label": "Rare Holo",
            "normalized_bucket": "holo rare",
            "odds_display": "1/5.6",
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "source_ids": ["fusion_strike_thepricedex_cross_reference_2026_05"],
            "caveat": "Best-available ThePriceDex cross-reference used for runtime; not SOURCE_DIRECT evidence.",
        },
        {
            "source_bucket_label": "Secret Rare",
            "normalized_bucket": "secret rare",
            "odds_display": "1/120",
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "source_ids": ["fusion_strike_thepricedex_cross_reference_2026_05"],
            "caveat": "Cross-reference/index row only; not source-direct runtime evidence.",
        },
        {
            "source_bucket_label": "Rainbow Rare",
            "normalized_bucket": "rainbow rare",
            "odds_display": "1/91.9",
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "source_ids": ["fusion_strike_thepricedex_cross_reference_2026_05"],
            "caveat": "Cross-reference/index row only; not source-direct runtime evidence.",
        },
        {
            "source_bucket_label": "Ultra Rare",
            "normalized_bucket": "ultra rare",
            "odds_display": "1/26.0",
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "source_ids": ["fusion_strike_thepricedex_cross_reference_2026_05"],
            "caveat": "Cross-reference/index row only; not source-direct runtime evidence.",
        },
        {
            "source_bucket_label": "Rare Holo VMAX",
            "normalized_bucket": "rare holo vmax",
            "odds_display": "1/26.5",
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "source_ids": ["fusion_strike_thepricedex_cross_reference_2026_05"],
            "caveat": "Cross-reference/index row only; not source-direct runtime evidence.",
        },
        {
            "source_bucket_label": "Rare Holo V",
            "normalized_bucket": "rare holo v",
            "odds_display": "1/11.1",
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "source_ids": ["fusion_strike_thepricedex_cross_reference_2026_05"],
            "caveat": "Cross-reference/index row only; not source-direct runtime evidence.",
        },
    ]
