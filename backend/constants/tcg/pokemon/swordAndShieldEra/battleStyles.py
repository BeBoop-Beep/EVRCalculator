from .baseConfig import BaseSetConfig

class SetBattleStylesConfig(BaseSetConfig):
    SET_NAME = 'Battle Styles'
    SET_ABBREVIATION = 'BST'
    SIMULATION_ENGINE = 'slot_schema'
    SLOT_SCHEMA_RUNTIME_ENABLED = True

    SET_ID = 'swsh5'
    RELEASE_DATE = '2021/03/19'
    PRINTED_TOTAL = 163
    TOTAL = 183
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh5/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2765/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2765/cards/?rows=5000&productTypeID=25'
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
            + (1 / 7.5)
            + (1 / 24)
            + (1 / 56)
            + (1 / 120)
            + (1 / 96)
            + (1 / 170)
        ),
        "holo rare": 1 / 3,
        "regular v": 1 / 7.5,
        "regular vmax": 1 / 24,
        "full art": 1 / 56,
        "rainbow rare": 1 / 120,
        "gold rare": 1 / 96,
        "alternate art v": 1 / 170,
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
                "card_number_max": 163,
                "name_pattern": "endswith(' V')",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "regular vmax": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 163,
                "name_contains": "VMAX",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "full art": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_range": "143-163",
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
                "card_number_range": "164-179",
                "name_not_contains": "Alternate",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "gold rare": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "180-183",
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
            "Battle Styles source confidence is weaker than later TCGplayer 8k+ set studies. "
            "ThePriceDex is cross-reference/index-only metadata and must not be treated as SOURCE_DIRECT."
        ),
        "blocking_reasons": [],
    }

    BATTLE_STYLES_PULL_RATE_REFERENCE_SOURCES = [
        {
            "source_id": "battle_styles_community_pack_study",
            "source_name": "Battle Styles community pull-rate pack study",
            "source_url": "https://www.reddit.com/r/PokemonTCG/",
            "source_type": "community_aggregation",
            "source_confidence": "medium",
            "discovered_via": "community pull-rate chart with explicit pack count",
            "notes": (
                "Primary community empirical source used for broad-bucket runtime modeling. "
                "Not official Pokemon-published odds."
            ),
        },
        {
            "source_id": "battle_styles_thepricedex_cross_reference_2026_05",
            "source_name": "ThePriceDex Battle Styles pull-rate cross-reference",
            "source_url": "https://www.thepricedex.com/set/swsh5/battle-styles/pull-rates",
            "source_type": "secondary_index",
            "source_confidence": "medium_low",
            "discovered_via": "ThePriceDex set cross-reference index",
            "notes": (
                "Cross-reference/index-only source pointer. ThePriceDex-only inferred or equal-distribution rows "
                "must not be promoted to SOURCE_DIRECT runtime evidence."
            ),
        },
        {
            "source_id": "battle_styles_elite_fourum_supplement",
            "source_name": "Elite Fourum Battle Styles pull-rate discussion",
            "source_url": "https://www.elitefourum.com/",
            "source_type": "supplementary_discussion",
            "source_confidence": "medium_low",
            "discovered_via": "Elite Fourum supplementary analysis",
            "notes": "Supplementary context only; not used as sole SOURCE_DIRECT authority.",
        },
    ]

    BATTLE_STYLES_PULL_RATE_REFERENCE_BUCKET_EVIDENCE = [
        {
            "source_bucket_label": "V",
            "normalized_bucket": "regular v",
            "odds_display": "1/7.5",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["battle_styles_community_pack_study"],
            "caveat": "Community empirical sample; confidence is medium.",
        },
        {
            "source_bucket_label": "VMAX",
            "normalized_bucket": "regular vmax",
            "odds_display": "1/24",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["battle_styles_community_pack_study"],
            "caveat": "Broad direct source bucket retained without unsupported child split.",
        },
        {
            "source_bucket_label": "Full Art",
            "normalized_bucket": "full art",
            "odds_display": "1/56",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["battle_styles_community_pack_study"],
            "caveat": "Modeled as broad full-art bucket; child rows are not forced.",
        },
        {
            "source_bucket_label": "Alternate Art V",
            "normalized_bucket": "alternate art v",
            "odds_display": "1/170",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["battle_styles_community_pack_study"],
            "caveat": "Only direct alternate-art row supported by local taxonomy.",
        },
        {
            "source_bucket_label": "Rainbow Rare",
            "normalized_bucket": "rainbow rare",
            "odds_display": "1/120",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["battle_styles_community_pack_study"],
            "caveat": "Direct broad bucket retained; no unsupported trainer/pokemon child split.",
        },
        {
            "source_bucket_label": "Gold Rare",
            "normalized_bucket": "gold rare",
            "odds_display": "1/96",
            "source_status": "SOURCE_DIRECT",
            "source_granularity_status": "SOURCE_DIRECT",
            "used_in_runtime": True,
            "source_ids": ["battle_styles_community_pack_study"],
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
            "source_status": "MISSING_SOURCE",
            "source_granularity_status": "MISSING_SOURCE",
            "used_in_runtime": False,
            "source_ids": [],
            "caveat": "Battle Styles has no Trainer Gallery runtime bucket.",
        },
        {
            "source_bucket_label": "VSTAR",
            "normalized_bucket": "regular vstar",
            "odds_display": None,
            "source_status": "MISSING_SOURCE",
            "source_granularity_status": "MISSING_SOURCE",
            "used_in_runtime": False,
            "source_ids": [],
            "caveat": "Battle Styles predates VSTAR taxonomy.",
        },
        {
            "source_bucket_label": "ThePriceDex inferred row",
            "normalized_bucket": "thepricedex inferred",
            "odds_display": None,
            "source_status": "SECONDARY_INDEX_ONLY",
            "source_granularity_status": "SECONDARY_INDEX_ONLY",
            "used_in_runtime": False,
            "source_ids": ["battle_styles_thepricedex_cross_reference_2026_05"],
            "caveat": "Index-only row must never be treated as SOURCE_DIRECT.",
        },
    ]
