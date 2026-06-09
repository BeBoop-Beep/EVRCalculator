from .baseConfig import BaseSetConfig


def _validate_chilling_reign_source_bucket_mapping(mapping):
    direct_rows = {
        source_row
        for source_row, details in mapping.items()
        if details.get("used_as_direct_outcome")
    }

    for source_row, details in mapping.items():
        children = details.get("children", ())
        if not details.get("used_as_direct_outcome"):
            continue
        overlap = direct_rows.intersection(children)
        if overlap:
            overlap_rows = ", ".join(sorted(overlap))
            raise ValueError(
                "Chilling Reign source bucket mapping is invalid: "
                f"parent source row {source_row!r} is marked as a direct outcome while child row(s) "
                f"{overlap_rows} are also marked direct. This double-counts overlapping categories."
            )

class SetChillingReignConfig(BaseSetConfig):
    SET_NAME = 'Chilling Reign'
    SET_ABBREVIATION = 'CRE'
    SIMULATION_ENGINE = 'slot_schema'
    SLOT_SCHEMA_RUNTIME_ENABLED = True

    SET_ID = 'swsh6'
    RELEASE_DATE = '2021/06/18'
    PRINTED_TOTAL = 198
    TOTAL = 233
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh6/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh6/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2807/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2807/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # Scaffold parity with SV/Mega config conventions:
    # - PULL_RATE_MAPPING
    # - REVERSE_SLOT_PROBABILITIES
    # - RARE_SLOT_PROBABILITY
    # Historical pre-promotion scaffolding is retained for traceability.
    # Project 6.9 promoted the best-available empirical draft table to
    # production RARE_SLOT_PROBABILITY after strict DB-source validation.
    #
    # IMPORTANT: User-provided CharizardX transcription rows are the controlling
    # swsh6 source for supported rare-slot outcomes. Base outcomes without direct
    # source rows remain explicit residual/provisional entries.
    # TODO: Populate set-wide pull-rate mapping when complete, non-overlapping
    # source-backed rates are available.
    PULL_RATE_MAPPING = {}

    # Reverse slot remains the same safe standard SWSH assumption scaffold:
    # one reverse slot with regular reverse at full mass.
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1.0,
        },
    }

    # Historical note: before Project 6.9 this set intentionally had no
    # production RARE_SLOT_PROBABILITY and runtime remained disabled.
    # Current intentional state: SLOT_SCHEMA_RUNTIME_ENABLED is True and
    # production RARE_SLOT_PROBABILITY equals
    # CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT.

    # Manually transcribed source buckets from user-provided CharizardX rows.
    # These are normalized before any runtime probability table is introduced.
    CHILLING_REIGN_SOURCE_BUCKET_MAPPING = {
        # Literal source rows from the CharmanderHelps image are treated as direct evidence.
        "VMAX": {
            "normalized_bucket": "vmax",
            "used_as_direct_outcome": True,
            "children": (),
            "notes": "Literal source row maps to regular VMAX runtime bucket.",
        },
        "Full Art": {
            "normalized_bucket": "full art",
            "used_as_direct_outcome": False,
            "children": ("Full Art V", "Full Art Trainer", "Full Art Alt"),
            "notes": "Parent summary bucket; do not model directly with child rows.",
        },
        "Rainbow": {
            "normalized_bucket": "rainbow rare",
            "used_as_direct_outcome": True,
            "children": (),
            "notes": "Broad source row is used directly; child split rows are intentionally collapsed.",
        },
        # Preferred direct simulator outcome rows (mutually exclusive target buckets).
        "Full Art V": {
            "normalized_bucket": "full art v",
            "used_as_direct_outcome": True,
            "children": (),
        },
        "Full Art Trainer": {
            "normalized_bucket": "full art trainer",
            "used_as_direct_outcome": True,
            "children": (),
        },
        "Full Art Alt": {
            "normalized_bucket": "alternate art v",
            "used_as_direct_outcome": True,
            "children": (),
        },
        "VMAX Alt": {
            "normalized_bucket": "alternate art vmax",
            "used_as_direct_outcome": True,
            "children": (),
        },
        "Gold": {
            "normalized_bucket": "gold rare",
            "used_as_direct_outcome": True,
            "children": (),
        },
        # Named-card rows are observed sanity checks only; never direct outcome buckets.
        "Gold Snorlax": {
            "normalized_bucket": "named-card-observation",
            "used_as_direct_outcome": False,
            "children": (),
            "notes": "Named card observation only; not a simulator bucket weight.",
        },
        "Ice Calyrex VMAX Alt": {
            "normalized_bucket": "named-card-observation",
            "used_as_direct_outcome": False,
            "children": (),
            "notes": "Named card observation only; not a simulator bucket weight.",
        },
        "Shadow Calyrex VMAX Alt": {
            "normalized_bucket": "named-card-observation",
            "used_as_direct_outcome": False,
            "children": (),
            "notes": "Named card observation only; not a simulator bucket weight.",
        },
        "Blaziken VMAX Alt": {
            "normalized_bucket": "named-card-observation",
            "used_as_direct_outcome": False,
            "children": (),
            "notes": "Named card observation only; not a simulator bucket weight.",
        },
    }

    CHILLING_REIGN_SOURCE_BUCKET_SANITY_CHECKS = {
        "VMAX": "1/22",
        "Full Art": "1/29",
        "Rainbow": "1/83",
        "Gold": "1/96",
        "Full Art V": "1/47",
        "Full Art Trainer": "1/74",
        "Rainbow Trainer": "1/151",
        "Rainbow VMAX": "1/189",
        "Full Art Alt": "1/109",
        "VMAX Alt": "1/396",
        "Gold Snorlax": "1/756",
        "Ice Calyrex VMAX Alt": "1/924",
        "Shadow Calyrex VMAX Alt": "1/1188",
        "Blaziken VMAX Alt": "1/1663",
    }

    # Direct source odds are intentionally stored separately from parent and
    # named-card sanity checks so downstream probability modeling can avoid
    # double-counting overlapping source categories.
    CHILLING_REIGN_SOURCE_DIRECT_BUCKET_ODDS = {
        "VMAX": "1/22",
        "Full Art V": "1/47",
        "Full Art Trainer": "1/74",
        "Rainbow": "1/83",
        "Gold": "1/96",
        "Full Art Alt": "1/109",
        "VMAX Alt": "1/396",
    }

    # Project 5.5: Rare-slot probability coverage audit.
    # This ledger records what is source-backed today and what remains unresolved
    # before a non-overlapping RARE_SLOT_PROBABILITY table can be introduced.
    CHILLING_REIGN_RARE_SLOT_COVERAGE_AUDIT = {
        "status": "incomplete",
        "can_construct_non_overlapping_rare_slot_table": False,
        "rare_is_residual_capable": True,
        "rare_requires_direct_source_row": False,
        "source_backed_direct_rows": {
            "VMAX": "1/22",
            "Full Art V": "1/47",
            "Full Art Trainer": "1/74",
            "Rainbow": "1/83",
            "Gold": "1/96",
            "Full Art Alt": "1/109",
            "VMAX Alt": "1/396",
        },
        "missing_non_residual_outcomes_blocking_rare_slot_probability": [
            "holo rare",
            "regular v",
        ],
        "high_rarity_source_specific_ambiguities": [
            (
                "charizardx_rows_provide_broader_rainbow_and_gold_categories_that_"
                "must_map_to_rainbow_rare_and_gold_rare_without_child_split_rows"
            ),
        ],
        "secondary_source_cross_checks": {
            "dripshop_qualitative": [
                "holo around one in three packs",
                "ultra rare around one in five to six packs",
                "full art or alt art around one in seventeen packs",
                "secret rare around one in sixty-seven packs",
            ],
            "reddit_thread_comments": [
                "regular V roughly one in 7.5 packs",
                "VMAX roughly one in 24 packs",
                "gold-card family roughly one in 100 packs",
            ],
            "notes": (
                "Secondary sources provide useful directional corroboration but do "
                "not yet provide a complete, non-overlapping rare-slot partition."
            ),
        },
        "api_rarity_snapshot_context": {
            "set_id": "swsh6",
            "observed_rows_in_rare_family": 144,
            "grouping_snapshot": {
                "high_rarity_grouped": 74,
                "holo_rare": 24,
                "rare": 23,
                "regular_v": 15,
                "regular_vmax": 8,
            },
            "notes": (
                "API counts describe card inventory composition, not pull probability mass."
            ),
        },
        "decision": (
            "Historical pre-promotion decision: keep runtime disabled under a strict direct-source "
            "criterion until missing non-residual outcomes are source-backed in a non-overlapping table "
            "and high-rarity source-row semantics are unambiguous. Superseded by Project 6.6-6.9 "
            "best-available empirical promotion after strict DB-source validation."
        ),
    }

    CHILLING_REIGN_PULL_RATE_SOURCE_NOTES = {
        "source": "PokemonTCG_Deals / CharmanderHelps Chilling Reign pull-rate post",
        "source_aliases": [
            "PokemonTCG_Deals",
            "@CharmanderHelps",
            "CharizardX",
            "CharmanderHelps/X",
        ],
        "coverage_scope": (
            "High-rarity source buckets only; this scaffold does not cover base "
            "holo rare/regular v outcomes and is not a complete rare-slot table."
        ),
        "historical_label": "Previously labeled CharizardX/user-provided transcription.",
        "rare_residual_policy": (
            "rare is residual-capable and does not require a direct source row."
        ),
        "named_card_rows_policy": (
            "Named-card odds are observed sanity checks only and are not used as per-card "
            "simulation weights or direct outcome probabilities."
        ),
        "parent_bucket_policy": (
            "Broad rows (VMAX, Full Art, Rainbow) are parent/sanity buckets and must not "
            "be modeled directly when child buckets are active."
        ),
        "source_blockers_focus": [
            "holo rare",
            "regular v",
            "unsupported child split rows under broader rainbow/gold source categories",
        ],
        "runtime_policy": (
            "Historical pre-promotion policy retained for traceability. Current Project 6.9 state: "
            "SLOT_SCHEMA_RUNTIME_ENABLED is True and production RARE_SLOT_PROBABILITY equals the "
            "best-available empirical draft table."
        ),
    }

    CHILLING_REIGN_PULL_RATE_SOURCE_LINKS = {
        "charizardx_user_rows": "https://x.com/CharmanderHelps/status/1417261446761680898",
        "swsh6_thepricedex_cross_reference_2026_06_holo": "https://www.thepricedex.com/pokemon/swsh06-chilling-reign/pull-rates",
        "dripshop_directional": "https://www.dripshop.live/blog/pokemon-trading-cards/chilling-reign-pull-rates---full-breakdown--rarest-cards",
        "reddit_directional": "https://www.reddit.com/r/PokemonTCG/comments/o2nhez/chilling_reign_pull_rate_data_from_5000_packs/",
    }

    # Project 5.5.2: Read-only Supabase card/variant label audit snapshot for swsh6.
    # This is a compact summary of the generated artifact at:
    # logs/audits/chilling_reign_supabase_label_audit_swsh6.json
    CHILLING_REIGN_DB_LABEL_AUDIT = {
        "source": "Supabase card/variant audit (read-only)",
        "set_id": "swsh6",
        "set_name": "Chilling Reign",
        "resolved_set_row_id": "1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890",
        "tables_audited": [
            "cards",
            "card_variants",
            "card_variant_price_observations",
            "card_market_usd_latest_by_condition",
            "simulation_input_cards",
            "simulation_input_cards_with_near_mint_price",
        ],
        "row_counts": {
            "cards": 233,
            "card_variants": 369,
            "latest_market_rows_for_set_variants": 1361,
            "price_observation_rows_for_set_variants": 2000,
        },
        "card_level_fields_observed": [
            "card_number",
            "created_at",
            "id",
            "image_large_url",
            "image_last_synced_at",
            "image_small_url",
            "name",
            "pokemon_tcg_api_id",
            "rarity",
            "set_id",
        ],
        "variant_level_fields_observed": [
            "card_id",
            "created_at",
            "edition",
            "id",
            "image_large_url",
            "image_last_synced_at",
            "image_small_url",
            "pokemon_tcg_api_id",
            "printing_type",
            "special_type",
        ],
        "card_level_distinct_summary": {
            "rarity_counts": {
                "Common": 43,
                "Uncommon": 46,
                "Rare": 23,
                "Holo Rare": 24,
                "Ultra Rare": 62,
                "Secret Rare": 35,
            },
            "supertype_counts": {"<NULL>": 233},
            "subtype_combo_counts": {"<NONE>": 233},
        },
        "variant_level_distinct_summary": {
            "printing_type_counts": {
                "non-holo": 112,
                "reverse-holo": 136,
                "holo": 121,
            },
            "special_type_counts": {"<NULL>": 369},
            "edition_counts": {"<NULL>": 369},
            "reverse_representation_counts": {"reverse-holo": 136},
        },
        "rare_slot_candidate_labels_found": {
            "regular rare": 46,
            "holo rare": 48,
            "regular v": 15,
            "regular vmax": 8,
            "full art v": 31,
            "alternate art v": 10,
            "alternate art vmax": 3,
            "gold/secret rare": 35,
        },
        "config_bucket_to_db_label_gaps": {
            "matched": [
                "full art v",
                "alternate art v",
                "alternate art vmax",
                "gold secret rare",
            ],
            "unmatched": [
                "full art trainer",
                "rainbow trainer",
                "rainbow vmax",
            ],
        },
        "requires_outcome_pool_mapping": True,
        "notes": (
            "Current swsh6 card/variant rows do not expose trainer/rainbow/alt families as explicit "
            "structured variant labels. Outcome-to-pool mapping must be config-controlled before "
            "introducing RARE_SLOT_PROBABILITY."
        ),
    }

    # Project 5.5.3: read-only outcome-to-pool mapping audit derived from
    # Supabase swsh6 card/variant rows.
    CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT = {
        "source": "Supabase cards + card_variants (read-only)",
        "set_id": "swsh6",
        "set_name": "Chilling Reign",
        "resolved_set_row_id": "1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890",
        "reverse_variant_policy": "exclude reverse-holo from rare-slot outcomes",
        "notes": (
            "Rare-slot membership is separated into card-level and variant-level pools. "
            "Reverse-holo variants belong to reverse-slot modeling only."
        ),
        "outcomes": {
            "rare": {
                "source": "Supabase rarity + printing_type",
                "card_filter": {"rarity": "Rare"},
                "variant_filter": {"printing_type": "non-holo"},
                "include_reverse_variants": False,
                "card_pool_count": 23,
                "variant_pool_count": 23,
                "identifiability": "db_fields_only",
            },
            "holo rare": {
                "source": "Supabase rarity + printing_type",
                "card_filter": {"rarity": "Holo Rare"},
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 24,
                "variant_pool_count": 24,
                "identifiability": "db_fields_only",
            },
            "regular v": {
                "source": "Supabase rarity + card_number + card name + printing_type",
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "card_number_max": 159,
                    "name_pattern": "endswith(' V')",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 15,
                "variant_pool_count": 15,
                "identifiability": "db_fields_with_card_number_and_name",
            },
            "regular vmax": {
                "source": "Supabase rarity + card_number + card name + printing_type",
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "card_number_max": 159,
                    "name_contains": "VMAX",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 8,
                "variant_pool_count": 8,
                "identifiability": "db_fields_with_card_number_and_name",
            },
            "full art v": {
                "source": "Supabase rarity + card_number + card name",
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "card_number_range": "160-185",
                    "name_contains": "(Full Art)",
                    "name_not_contains": "Alternate",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 16,
                "variant_pool_count": 16,
                "identifiability": "derived_from_card_number_range_and_name",
            },
            "full art trainer": {
                "source": "Supabase rarity + card_number range",
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "card_number_range": "186-198",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 13,
                "variant_pool_count": 13,
                "identifiability": "derived_from_card_number_range",
            },
            "alternate art v": {
                "source": "Supabase rarity + card name",
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "name_contains": "(Alternate Full Art)",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 10,
                "variant_pool_count": 10,
                "identifiability": "derived_from_card_name",
            },
            "alternate art vmax": {
                "source": "Supabase rarity + card name",
                "card_filter": {
                    "rarity": "Secret Rare",
                    "name_contains": "Alternate Art Secret",
                    "name_contains_all": ["VMAX"],
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 3,
                "variant_pool_count": 3,
                "identifiability": "derived_from_card_name",
            },
            "rainbow rare": {
                "source": "Supabase rarity + card_number range",
                "card_filter": {
                    "rarity": "Secret Rare",
                    "card_number_range": "199-221",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 20,
                "variant_pool_count": 20,
                "identifiability": "derived_from_card_number_range",
            },
            "gold rare": {
                "source": "Supabase rarity + card_number range",
                "card_filter": {
                    "rarity": "Secret Rare",
                    "card_number_range": "222-233",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 12,
                "variant_pool_count": 12,
                "identifiability": "derived_from_card_number_range",
            },
        },
        "high_rarity_bucket_resolution_status": {
            "full art v": "can be derived from card number ranges and card names",
            "full art trainer": "can be derived from card number ranges",
            "alternate art v": "can be derived from card names",
            "alternate art vmax": "can be derived from card names",
            "rainbow rare": "collapsed broad source bucket from Rainbow row",
            "gold rare": "collapsed broad source bucket from Gold row",
        },
        "requires_manual_mapping": False,
        "requires_pokemon_tcg_api_metadata_refresh": False,
        "blocked": False,
    }

    # Runtime slot-schema pool contract. Keep this separate from the
    # audit object so documentation evidence and runtime configuration are
    # decoupled.
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
                "card_number_max": 159,
                "name_pattern": "endswith(' V')",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "regular vmax": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 159,
                "name_contains": "VMAX",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "full art v": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_range": "160-185",
                "name_contains": "(Full Art)",
                "name_not_contains": "Alternate",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "full art trainer": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_range": "186-198",
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
        "alternate art vmax": {
            "source": "rarity + name",
            "card_filter": {
                "rarity": "Secret Rare",
                "name_contains": "Alternate Art Secret",
                "name_contains_all": ["VMAX"],
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "rainbow rare": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "199-221",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "gold rare": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "222-233",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
    }

    # Project 6.1.1: Compact bucket classification audit summary.
    # Full ledger: backend/docs/audits/CHILLING_REIGN_BUCKET_CLASSIFICATION_LEDGER.md
    CHILLING_REIGN_BUCKET_CLASSIFICATION_AUDIT = {
        "status": "complete",
        "source": "Supabase card/variant rows + SLOT_SCHEMA_OUTCOME_POOL_MAPPING",
        "eligible_non_reverse_rare_family_variants": 144,
        "mapped_variants": 144,
        "unmapped_variants": 0,
        "overlapping_variants": 0,
        "count_reconciliation_note": (
            "Earlier planning target of 132 conflicts with validated bucket counts; "
            "the listed per-bucket totals sum to 144 and the ledger confirms 144 mapped variants."
        ),
        "ambiguous_name_examples": {
            "Blaziken V (#020)": "regular v",
            "Blaziken V (Full Art) (#161)": "full art v",
            "Blaziken V (Alternate Full Art)": "alternate art v",
            "Blaziken VMAX (#021)": "regular vmax",
            "Blaziken VMAX (Secret) (#200)": "rainbow rare",
            "Blaziken VMAX (Alternate Art Secret) (#201)": "alternate art vmax",
            "Snorlax (Secret) (#224)": "gold rare",
        },
        "notes": (
            "Rarity alone is insufficient; bucket resolution uses rarity + card_number + name. "
            "rare is residual-capable and does not require a direct source row."
        ),
    }

    # Project 5.5.4: Source-odds vs pool-count sanity audit.
    # This is a read-only consistency check only; it does not define runtime
    # probabilities and does not convert named-card observations into weights.
    CHILLING_REIGN_SOURCE_ODDS_POOL_COUNT_SANITY_AUDIT = {
        "status": "acceptable_with_named_card_noise",
        "method": (
            "Compare direct bucket odds to eligible card counts using uniform-within-bucket "
            "implied per-card math; use named-card rows only as sanity observations."
        ),
        "direct_bucket_checks": {
            "full art v": {
                "source_bucket_odds": "1/47",
                "bucket_probability": 1 / 47,
                "eligible_card_count": 16,
                "implied_uniform_per_card_probability": (1 / 47) / 16,
                "implied_uniform_per_card_odds": "1/752",
                "implied_uniform_per_card_one_in_packs": 752,
                "notes": "Derived from direct bucket odds and mapped card pool count.",
            },
            "full art trainer": {
                "source_bucket_odds": "1/74",
                "bucket_probability": 1 / 74,
                "eligible_card_count": 13,
                "implied_uniform_per_card_probability": (1 / 74) / 13,
                "implied_uniform_per_card_odds": "1/962",
                "implied_uniform_per_card_one_in_packs": 962,
                "notes": "Derived from direct bucket odds and mapped card pool count.",
            },
            "alternate art v": {
                "source_bucket_odds": "1/109",
                "bucket_probability": 1 / 109,
                "eligible_card_count": 10,
                "implied_uniform_per_card_probability": (1 / 109) / 10,
                "implied_uniform_per_card_odds": "1/1090",
                "implied_uniform_per_card_one_in_packs": 1090,
                "notes": "Derived from direct bucket odds and mapped card pool count.",
            },
            "alternate art vmax": {
                "source_bucket_odds": "1/396",
                "bucket_probability": 1 / 396,
                "eligible_card_count": 3,
                "implied_uniform_per_card_probability": (1 / 396) / 3,
                "implied_uniform_per_card_odds": "1/1188",
                "implied_uniform_per_card_one_in_packs": 1188,
                "notes": "Derived from direct bucket odds and mapped card pool count.",
            },
            "rainbow rare": {
                "source_bucket_odds": "1/83",
                "bucket_probability": 1 / 83,
                "eligible_card_count": 20,
                "implied_uniform_per_card_probability": (1 / 83) / 20,
                "implied_uniform_per_card_odds": "1/1660",
                "implied_uniform_per_card_one_in_packs": 1660,
                "notes": "Derived from direct bucket odds and mapped card pool count.",
            },
            "gold rare": {
                "source_bucket_odds": "1/96",
                "bucket_probability": 1 / 96,
                "eligible_card_count": 12,
                "implied_uniform_per_card_probability": (1 / 96) / 12,
                "implied_uniform_per_card_odds": "1/1152",
                "implied_uniform_per_card_one_in_packs": 1152,
                "notes": "Derived from direct bucket odds and mapped card pool count.",
            },
        },
        "named_card_sanity_checks": {
            "policy": "observation_only_never_used_as_weights",
            "expected_from_bucket_uniform_model": {
                "gold rare per-card": "1/1152",
                "alternate art vmax per-card": "1/1188",
            },
            "gold_snorlax": {
                "observed_named_card_odds": "1/756",
                "expected_uniform_from_gold_bucket": "1/1152",
                "observed_vs_expected_probability_ratio": 1.5238095238,
                "interpretation": (
                    "Higher than uniform expectation; plausible source sampling/rounding noise or "
                    "bucket-semantics mismatch. Keep as sanity-only observation."
                ),
            },
            "vmax_alt_named_rows": {
                "expected_uniform_from_vmax_alt_bucket": "1/1188",
                "rows": {
                    "Ice Calyrex VMAX Alt": {
                        "observed_odds": "1/924",
                        "observed_vs_expected_probability_ratio": 1.2857142857,
                    },
                    "Shadow Calyrex VMAX Alt": {
                        "observed_odds": "1/1188",
                        "observed_vs_expected_probability_ratio": 1.0,
                    },
                    "Blaziken VMAX Alt": {
                        "observed_odds": "1/1663",
                        "observed_vs_expected_probability_ratio": 0.7143716176,
                    },
                },
                "interpretation": (
                    "Spread around uniform expectation suggests named-row noise and/or source-semantics drift; "
                    "do not treat named rows as per-card weights."
                ),
            },
        },
        "decision": (
            "Bucket-level semantics are internally plausible enough for Project 5.6 to draft a rare-slot "
            "probability table at bucket level only. Named-card rows remain sanity checks only and must not "
            "be converted into per-card weights."
        ),
        "runtime_guardrails": {
            "adds_rare_slot_probability": False,
            "slot_schema_runtime_enabled": False,
            "changes_runtime_behavior": False,
        },
    }

    # Project 6.6: Best-available empirical draft table for rare slot.
    # Project 6.9 promoted this draft table to production runtime for controlled
    # swsh6 enablement after strict DB-source validation.
    CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT = {
        "rare": 1
        - (
            (1 / 5.6)
            + (1 / 7.5)
            + (1 / 22)
            + (1 / 47)
            + (1 / 74)
            + (1 / 109)
            + (1 / 396)
            + (1 / 83)
            + (1 / 96)
        ),
        "holo rare": 1 / 5.6,
        "regular v": 1 / 7.5,
        "regular vmax": 1 / 22,
        "full art v": 1 / 47,
        "full art trainer": 1 / 74,
        "alternate art v": 1 / 109,
        "alternate art vmax": 1 / 396,
        "rainbow rare": 1 / 83,
        "gold rare": 1 / 96,
    }

    # Promoted to production runtime after strict DB-source validation.
    # Keep the *_DRAFT table and its audit ledger intact for traceability.
    RARE_SLOT_PROBABILITY = CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT

    # Project 6.6: Source-backed + assumption-documented empirical draft audit.
    CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT = {
        "status": "partially_source_locked_charizardx",
        "probability_model_status": "partially_source_locked_charizardx_with_provisional_rows",
        "runtime_remains_disabled": False,
        "source_label": "User-provided CharizardX posting transcription",
        "source_aliases": ["CharizardX", "CharmanderHelps/X"],
        "source_rows_used": {
            "VMAX": {
                "source_odds": "1/22",
                "normalized_bucket": "regular vmax",
                "probability": 1 / 22,
                "source_granularity_status": "SOURCE_DIRECT",
            },
            "Full Art V": {
                "source_odds": "1/47",
                "normalized_bucket": "full art v",
                "probability": 1 / 47,
                "source_granularity_status": "SOURCE_DIRECT",
            },
            "Full Art Trainer": {
                "source_odds": "1/74",
                "normalized_bucket": "full art trainer",
                "probability": 1 / 74,
                "source_granularity_status": "SOURCE_DIRECT",
            },
            "Full Art Alt": {
                "source_odds": "1/109",
                "normalized_bucket": "alternate art v",
                "probability": 1 / 109,
                "source_granularity_status": "SOURCE_DIRECT",
            },
            "VMAX Alt": {
                "source_odds": "1/396",
                "normalized_bucket": "alternate art vmax",
                "probability": 1 / 396,
                "source_granularity_status": "SOURCE_DIRECT",
            },
            "Rainbow": {
                "source_odds": "1/83",
                "normalized_bucket": "rainbow rare",
                "probability": 1 / 83,
                "source_granularity_status": "SOURCE_DIRECT",
            },
            "Gold": {
                "source_odds": "1/96",
                "normalized_bucket": "gold rare",
                "probability": 1 / 96,
                "source_granularity_status": "SOURCE_DIRECT",
            },
        },
        "source_rows_used_with_assumptions": {
            "dripshop_holo_directional": {
                "source_odds": "1/5.6",
                "normalized_bucket": "holo rare",
                "probability": 1 / 5.6,
                "source_granularity_status": "PROVISIONAL_DIRECTIONAL",
                "source_id": "swsh6_thepricedex_cross_reference_2026_06_holo",
                "assumption": (
                    "Best-available ThePriceDex cross-reference used as provisional holo-rare proxy. "
                    "This is secondary-index evidence and not SOURCE_DIRECT publisher odds."
                ),
            },
            "reddit_regular_v_directional": {
                "source_odds": "~1/7.5",
                "normalized_bucket": "regular v",
                "probability": 1 / 7.5,
                "source_granularity_status": "PROVISIONAL_DIRECTIONAL",
                "assumption": (
                    "Directional secondary source interpreted as regular V frequency; treated as draft empirical "
                    "estimate with documented uncertainty."
                ),
            },
        },
        "source_rows_rejected": {
            "Full Art": "parent/broad row excluded because cleaner direct child rows exist",
            "Rainbow Trainer": "unsupported split under broader Rainbow source row",
            "Rainbow VMAX": "unsupported split under broader Rainbow source row",
            "gold secret rare": "unsupported split under broader Gold source row",
            "Holo VMAX": "legacy alias row removed in favor of literal source label VMAX",
            "Golden Rare": "legacy alias row removed in favor of literal source label Gold",
            "Alt Art V": "legacy alias row removed in favor of literal source label Full Art Alt",
            "Alt Art Vmax": "legacy alias row removed in favor of literal source label VMAX Alt",
        },
        "parent_rows_used_with_assumptions": {},
        "named_card_rows_excluded": {
            "Gold Snorlax": "named_card_observation_rows_only",
            "Ice Calyrex VMAX Alt": "named_card_observation_rows_only",
            "Shadow Calyrex VMAX Alt": "named_card_observation_rows_only",
            "Blaziken VMAX Alt": "named_card_observation_rows_only",
        },
        "final_normalized_table": CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT,
        "residual_rare_probability": CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT["rare"],
        "probability_sum": sum(CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT.values()),
        "direct_high_rarity_mass": {
            "regular vmax": 1 / 22,
            "full art v": 1 / 47,
            "full art trainer": 1 / 74,
            "alternate art v": 1 / 109,
            "alternate art vmax": 1 / 396,
            "rainbow rare": 1 / 83,
            "gold rare": 1 / 96,
            "sum": (
                (1 / 22)
                + (1 / 47)
                + (1 / 74)
                + (1 / 109)
                + (1 / 396)
                + (1 / 83)
                + (1 / 96)
            ),
        },
        "remaining_base_mass": 1
        - (
            (1 / 22)
            + (1 / 47)
            + (1 / 74)
            + (1 / 109)
            + (1 / 396)
            + (1 / 83)
            + (1 / 96)
        ),
        "base_outcome_source_decisions": {
            "rare": {
                "source_available": True,
                "decision": "SOURCE_DERIVED_RESIDUAL",
                "reason": (
                    "rare is residual-capable and does not require a direct source row once all "
                    "non-rare outcomes are source-backed with non-overlapping semantics."
                ),
            },
            "holo rare": {
                "source_available": True,
                "decision": "PROVISIONAL_DIRECTIONAL",
                "reason": (
                    "Best-available ThePriceDex cross-reference (1/5.6) is used as provisional secondary "
                    "input with explicit non-direct caveat."
                ),
            },
            "regular v": {
                "source_available": True,
                "decision": "PROVISIONAL_DIRECTIONAL",
                "reason": (
                    "Secondary claim 'regular V roughly one in 7.5 packs' is used as best-available empirical "
                    "draft input with explicit assumption flag."
                ),
            },
            "regular vmax": {
                "source_available": True,
                "decision": "SOURCE_DIRECT",
                "reason": (
                    "Direct user-provided VMAX row maps to regular vmax at 1/22."
                ),
            },
        },
        "source_specific_high_rarity_ambiguities": [
            (
                "Rainbow Trainer and Rainbow VMAX splits are unsupported under the broad Rainbow source row; "
                "gold secret rare split is unsupported under Gold source row"
            ),
        ],
        "legacy_probability_sum_field": None,
        "direct_bucket_source": "CHILLING_REIGN_SOURCE_DIRECT_BUCKET_ODDS",
        "base_mass_resolution_policy": (
            "Residualization to rare is applied in this draft model using best-available empirical rows and "
            "documented assumptions."
        ),
        "missing_source_rows": {
            "regular v": "MISSING_SOURCE",
            "holo rare": "MISSING_SOURCE",
            "rare": "SOURCE_DERIVED_RESIDUAL",
        },
        "unsupported_split_rows": {
            "rainbow trainer": "UNSUPPORTED_SPLIT",
            "rainbow vmax": "UNSUPPORTED_SPLIT",
            "gold secret rare": "UNSUPPORTED_SPLIT",
        },
        "parent_rows_excluded": True,
        "decision": (
            "Project 16.17: swsh6 is partially source-locked to user-provided CharizardX rows. "
            "Buckets supported by direct rows are locked exactly; rare remains residual and holo rare/regular v "
            "remain provisional directional pending direct source rows."
        ),
    }

    # Project 6.9: Runtime candidate state based on best-available empirical
    # evidence. Historical blockers remain in earlier audit ledgers for context.
    SLOT_SCHEMA_SOURCE_CONFIDENCE = {
        "status": "runtime_candidate_best_available_empirical",
        "runtime_ready": True,
        "pool_mapping_ready": True,
        "bucket_classification_ready": True,
        "rare_slot_probability_ready": True,
        "reverse_slot_probability_ready": True,
        "source_model": "best_available_empirical",
        "source_caveat": (
            "Not official Pokemon pull rates; derived from public empirical samples and documented assumptions."
        ),
        "blocking_reasons": [],
    }

    @classmethod
    def get_chilling_reign_direct_outcome_buckets(cls):
        mapping = getattr(cls, "CHILLING_REIGN_SOURCE_BUCKET_MAPPING", {})
        _validate_chilling_reign_source_bucket_mapping(mapping)
        return {
            details["normalized_bucket"]
            for details in mapping.values()
            if details.get("used_as_direct_outcome")
        }

    @classmethod
    def validate_chilling_reign_source_bucket_mapping(cls):
        _validate_chilling_reign_source_bucket_mapping(cls.CHILLING_REIGN_SOURCE_BUCKET_MAPPING)
