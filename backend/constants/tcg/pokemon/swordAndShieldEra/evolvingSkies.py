from .baseConfig import BaseSetConfig

class SetEvolvingSkiesConfig(BaseSetConfig):
    SET_NAME = 'Evolving Skies'
    SET_ABBREVIATION = 'EVS'
    SIMULATION_ENGINE = 'slot_schema'
    SLOT_SCHEMA_RUNTIME_ENABLED = True

    SET_ID = 'swsh7'
    RELEASE_DATE = '2021/08/27'
    PRINTED_TOTAL = 203
    TOTAL = 237
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh7/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh7/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2848/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2848/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # Historical pre-promotion scaffold retained for traceability.
    # Project 6.9 promoted best-available empirical rare-slot probabilities to
    # controlled runtime while preserving source evidence below.
    PULL_RATE_MAPPING = {}

    # Reverse slot remains the safe standard SWSH assumption scaffold:
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
    # EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT.

    # Project 6.0: Read-only Supabase card/variant label audit snapshot for swsh7.
    EVOLVING_SKIES_DB_LABEL_AUDIT = {
        "source": "Supabase card/variant audit (read-only)",
        "set_id": "swsh7",
        "set_name": "Evolving Skies",
        "resolved_set_row_id": "93212749-ce0e-498e-975e-7d947a3448ce",
        "tables_audited": [
            "cards",
            "card_variants",
            "card_variant_price_observations",
            "card_market_usd_latest_by_condition",
            "simulation_input_cards",
            "simulation_input_cards_with_near_mint_price",
        ],
        "row_counts": {
            "cards": 237,
            "card_variants": 369,
            "latest_market_rows_for_set_variants": 1403,
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
                "Common": 42,
                "Uncommon": 51,
                "Rare": 19,
                "Holo Rare": 20,
                "Ultra Rare": 71,
                "Secret Rare": 34,
            },
            "supertype_counts": {"<NULL>": 237},
            "subtype_combo_counts": {"<NONE>": 237},
            "set_name_counts": {"<NULL>": 237},
            "card_number_presence": {
                "present": 237,
                "missing": 0,
            },
        },
        "variant_level_distinct_summary": {
            "printing_type_counts": {
                "reverse-holo": 132,
                "holo": 125,
                "non-holo": 112,
            },
            "special_type_counts": {"<NULL>": 369},
            "edition_counts": {"<NULL>": 369},
            "reverse_representation_counts": {"reverse-holo": 132},
        },
        "latest_market_distinct_summary": {
            "condition_counts": {
                "Near Mint": 369,
                "Lightly Played": 369,
                "Moderately Played": 361,
                "Heavily Played": 147,
                "Damaged": 157,
            },
            "source_counts": {"TCGPlayer": 1403},
            "currency_counts": {"USD": 1403},
        },
        "rare_slot_candidate_labels_found": {
            "rare": 19,
            "holo rare": 20,
            "regular v": 18,
            "regular vmax": 15,
            "full art": 27,
            "alternate art v": 11,
            "alternate art vmax": 6,
            "rainbow rare": 16,
            "gold rare": 12,
        },
        "notes": (
            "Current swsh7 card/variant rows do not expose structured trainer/alt/rainbow fields. "
            "Outcome-to-pool mapping relies on source-backed card_number and name filters."
        ),
    }

    # Project 6.0: Read-only outcome-to-pool mapping audit derived from swsh7.
    EVOLVING_SKIES_OUTCOME_POOL_MAPPING_AUDIT = {
        "source": "Supabase cards + card_variants (read-only)",
        "set_id": "swsh7",
        "set_name": "Evolving Skies",
        "resolved_set_row_id": "93212749-ce0e-498e-975e-7d947a3448ce",
        "reverse_variant_policy": "exclude reverse-holo from rare-slot outcomes",
        "coverage": {
            "eligible_non_reverse_rare_family_variants": 144,
            "mapped_variants": 144,
            "unmapped_variants": 0,
            "overlapping_variants": 0,
        },
        "outcomes": {
            "rare": {
                "card_filter": {"rarity": "Rare"},
                "variant_filter": {"printing_type": "non-holo"},
                "include_reverse_variants": False,
                "card_pool_count": 19,
                "variant_pool_count": 19,
                "identifiability": "db_fields_only",
            },
            "holo rare": {
                "card_filter": {"rarity": "Holo Rare"},
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 20,
                "variant_pool_count": 20,
                "identifiability": "db_fields_only",
            },
            "regular v": {
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "card_number_max": 203,
                    "name_pattern": "endswith(' V')",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 18,
                "variant_pool_count": 18,
                "identifiability": "db_fields_with_card_number_and_name",
            },
            "regular vmax": {
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "card_number_max": 203,
                    "name_contains": "VMAX",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 15,
                "variant_pool_count": 15,
                "identifiability": "db_fields_with_card_number_and_name",
            },
            "full art": {
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "card_number_range": "166-203",
                    "name_not_contains": "Alternate",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 27,
                "variant_pool_count": 27,
                "identifiability": "derived_from_card_number_range",
            },
            "alternate art v": {
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "name_contains": "(Alternate Full Art)",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 11,
                "variant_pool_count": 11,
                "identifiability": "derived_from_card_name",
            },
            "alternate art vmax": {
                "card_filter": {
                    "rarity": "Secret Rare",
                    "name_contains": "Alternate Art Secret",
                    "name_contains_all": ["VMAX"],
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 6,
                "variant_pool_count": 6,
                "identifiability": "derived_from_card_name",
            },
            "rainbow rare": {
                "card_filter": {
                    "rarity": "Secret Rare",
                    "card_number_range": "204-225",
                    "name_not_contains": "Alternate",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 16,
                "variant_pool_count": 16,
                "identifiability": "derived_from_card_number_range",
            },
            "gold rare": {
                "card_filter": {
                    "rarity": "Secret Rare",
                    "card_number_range": "226-237",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 12,
                "variant_pool_count": 12,
                "identifiability": "derived_from_card_number_range",
            },
        },
        "requires_manual_mapping": False,
        "blocked": False,
    }

    # Runtime slot-schema pool contract.
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
                "card_number_max": 203,
                "name_pattern": "endswith(' V')",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "regular vmax": {
            "source": "rarity + card_number + name + printing_type",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_max": 203,
                "name_contains": "VMAX",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "full art": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_range": "166-203",
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
                "card_number_range": "204-225",
                "name_not_contains": "Alternate",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "gold rare": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "226-237",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
    }

    # Project 6.1: Compact bucket classification audit summary.
    # Full ledger: backend/docs/audits/EVOLVING_SKIES_BUCKET_CLASSIFICATION_LEDGER.md
    EVOLVING_SKIES_BUCKET_CLASSIFICATION_AUDIT = {
        "status": "complete",
        "source": "Supabase card/variant rows + SLOT_SCHEMA_OUTCOME_POOL_MAPPING",
        "eligible_non_reverse_rare_family_variants": 144,
        "mapped_variants": 144,
        "unmapped_variants": 0,
        "overlapping_variants": 0,
        "ambiguous_name_examples": {
            "Umbreon V (#094)": "regular v",
            "Umbreon V (Full Art) (#179)": "full art",
            "Umbreon V (Alternate Full Art) (#188)": "alternate art v",
            "Umbreon VMAX (#095)": "regular vmax",
            "Umbreon VMAX (#214, Secret Rare)": "rainbow rare",
            "Umbreon VMAX Alternate Art Secret (#215)": "alternate art vmax",
        },
        "notes": (
            "Rarity alone is insufficient; bucket resolution uses rarity + card_number + name. "
            "rare is residual-capable and does not require a direct source row."
        ),
    }

    # Project 6.6: Best-available empirical draft table for rare slot.
    # Project 6.9 promoted this draft table to production runtime for controlled
    # swsh7 enablement after strict DB-source validation.
    EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT = {
        "rare": 1
        - (
            (1 / 5.5)
            + 0.1056
            + 0.056
            + 0.0278
            + 0.0110
            + 0.0030
            + 0.0084
            + 0.0091
        ),
        "holo rare": 1 / 5.5,
        "regular v": 0.1056,
        "regular vmax": 0.056,
        "full art": 0.0278,
        "alternate art v": 0.0110,
        "alternate art vmax": 0.0030,
        "rainbow rare": 0.0084,
        "gold rare": 0.0091,
    }

    # Promoted to production runtime after strict DB-source validation.
    # Keep the *_DRAFT table and its audit ledger intact for traceability.
    RARE_SLOT_PROBABILITY = EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT

    EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT_AUDIT = {
        "status": "best_available_empirical_draft",
        "probability_model_status": "best_available_empirical_draft",
        "runtime_remains_disabled": True,
        "source_rows_used": {
            "Normal Pokemon V": {
                "source_odds": "10.56%",
                "normalized_bucket": "regular v",
                "probability": 0.1056,
                "source_family": "tcgplayer_evolving_skies_8000_pack",
            },
            "Normal Pokemon VMAX": {
                "source_odds": "5.60%",
                "normalized_bucket": "regular vmax",
                "probability": 0.056,
                "source_family": "tcgplayer_evolving_skies_8000_pack",
            },
            "Full-Art": {
                "source_odds": "2.78%",
                "normalized_bucket": "full art",
                "probability": 0.0278,
                "source_family": "tcgplayer_evolving_skies_8000_pack",
            },
            "Alt-Art Pokemon V": {
                "source_odds": "1.10%",
                "normalized_bucket": "alternate art v",
                "probability": 0.0110,
                "source_family": "tcgplayer_evolving_skies_8000_pack",
            },
            "Alt-Art Pokemon VMAX": {
                "source_odds": "0.30%",
                "normalized_bucket": "alternate art vmax",
                "probability": 0.0030,
                "source_family": "tcgplayer_evolving_skies_8000_pack",
            },
            "Rainbow Rare": {
                "source_odds": "0.84%",
                "normalized_bucket": "rainbow rare",
                "probability": 0.0084,
                "source_family": "tcgplayer_evolving_skies_8000_pack",
            },
            "Gold Rare": {
                "source_odds": "0.91%",
                "normalized_bucket": "gold rare",
                "probability": 0.0091,
                "source_family": "tcgplayer_evolving_skies_8000_pack",
            },
        },
        "source_rows_used_with_assumptions": {
            "holo_rare_secondary_directional": {
                "source_odds": "1/5.5",
                "normalized_bucket": "holo rare",
                "probability": 1 / 5.5,
                "source_granularity_status": "PROVISIONAL_DIRECTIONAL",
                "source_id": "swsh7_thepricedex_cross_reference_2026_06_holo",
                "assumption": (
                    "Best-available ThePriceDex cross-reference used as provisional holo-rare estimate; "
                    "not SOURCE_DIRECT evidence."
                ),
            },
        },
        "source_rows_rejected": {},
        "named_card_rows_excluded": {},
        "parent_rows_used_with_assumptions": {},
        "final_normalized_table": EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT,
        "residual_rare_probability": EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT["rare"],
        "probability_sum": sum(EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT.values()),
        "decision": (
            "Historical pre-promotion decision retained for audit traceability. Superseded by Project 6.9, "
            "which promoted this best-available empirical draft table to production RARE_SLOT_PROBABILITY "
            "and enabled controlled runtime after strict DB-source validation."
        ),
    }

    # Project 6.0+: Source-family audit for rare-slot probability readiness.
    EVOLVING_SKIES_PULL_RATE_SOURCE_AUDIT = {
        "source_families": {
            "charmanderhelps_x_image_sources": {
                "status": "historical_context_not_used_for_current_bucket_rates",
                "rows_transcribed": [],
                "notes": "Retained for traceability only; current swsh7 bucket rates follow source-level TCGplayer rows.",
            },
            "reddit_pull_rate_discussions": {
                "status": "used_for_primary_source_traceability",
                "references": [
                    "https://reddit.com/r/PokemonTCG/comments/1f35e2h/tcgplayers_evolving_skies_pull_rates_from_8000/",
                ],
                "rows_transcribed": [
                    "Normal Pokemon V: 10.56% (~1/9)",
                    "Normal Pokemon VMAX: 5.60% (~1/18)",
                    "Full-Art: 2.78% (~1/36)",
                    "Alt-Art Pokemon V: 1.10% (~1/91)",
                    "Alt-Art Pokemon VMAX: 0.30% (~1/332)",
                    "Rainbow Rare: 0.84% (~1/118)",
                    "Gold Rare: 0.91% (~1/109)",
                ],
                "notes": "Used as primary source-level empirical rows for bucket probabilities.",
            },
            "tcgplayer_evolving_skies_8000_pack": {
                "status": "used_as_primary_source",
                "references": [
                    "https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Evolving-Skies-Pull-Rates/6a743d7b-e5ee-4fd6-9d18-64a636990e8c/",
                ],
                "rows_transcribed": [
                    "Normal Pokemon V: 10.56%",
                    "Normal Pokemon VMAX: 5.60%",
                    "Full-Art: 2.78%",
                    "Alt-Art Pokemon V: 1.10%",
                    "Alt-Art Pokemon VMAX: 0.30%",
                    "Rainbow Rare: 0.84%",
                    "Gold Rare: 0.91%",
                ],
                "notes": "Primary source-level rates for swsh7 modeling granularity.",
            },
            "thepricedex_cross_reference": {
                "status": "secondary_index_cross_reference",
                "references": [
                    "https://www.thepricedex.com/pokemon/swsh07-evolving-skies/pull-rates",
                ],
                "rows_transcribed": [
                    "Rare Holo: 1 in 5.5",
                ],
                "notes": "Used as secondary-index cross-reference for holo rare; never treated as SOURCE_DIRECT.",
            },
        },
        "direct_non_overlapping_candidate_rows": {
            "normal pokemon v": "10.56% (~1/9)",
            "normal pokemon vmax": "5.60% (~1/18)",
            "full-art": "2.78% (~1/36)",
            "alt-art pokemon v": "1.10% (~1/91)",
            "alt-art pokemon vmax": "0.30% (~1/332)",
            "rainbow rare": "0.84% (~1/118)",
            "gold rare": "0.91% (~1/109)",
        },
        "parent_sanity_rows_only": {},
        "named_card_observation_rows_only": {},
        "unusable_or_overlapping_rows": {
            "rows_kept_observation_only": [],
        },
        "rare_slot_probability_readiness": {
            "can_construct_non_overlapping_source_backed_table": True,
            # rare is residual-capable: its probability = 1 - sum(all other rare-slot probabilities).
            # It does not need a direct source row.
            "rare_is_residual_capable": True,
            "rare_requires_direct_source_row": False,
            "missing_non_residual_outcomes": [],
            "high_rarity_overlap_status": "not_applicable_source_rows_non_overlapping",
            "parent_rows_excluded": True,
            "parent_rows_used_with_assumptions": False,
            "named_card_rows_excluded": False,
        },
        "decision": (
            "Historical strict direct-source gating note retained for traceability. Superseded by Project 6.6-6.9 "
            "best-available empirical model and controlled runtime promotion, where production "
            "RARE_SLOT_PROBABILITY equals EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT."
        ),
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
            "Not official Pokemon pull rates; derived from public empirical samples and documented assumptions."
        ),
        "blocking_reasons": [],
    }
