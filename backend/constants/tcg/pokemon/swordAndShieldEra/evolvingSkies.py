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
            "full art v": 22,
            "full art trainer": 5,
            "alternate art v": 11,
            "alternate art vmax": 6,
            "rainbow trainer": 5,
            "rainbow vmax": 11,
            "gold secret rare": 12,
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
            "full art v": {
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "card_number_range": "166-198",
                    "name_contains": "(Full Art)",
                    "name_not_contains": "Alternate",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 22,
                "variant_pool_count": 22,
                "identifiability": "derived_from_card_number_range_and_name",
            },
            "full art trainer": {
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "card_number_range": "199-203",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 5,
                "variant_pool_count": 5,
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
            "rainbow trainer": {
                "card_filter": {
                    "rarity": "Secret Rare",
                    "card_number_range": "221-225",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 5,
                "variant_pool_count": 5,
                "identifiability": "derived_from_card_number_range",
            },
            "rainbow vmax": {
                "card_filter": {
                    "rarity": "Secret Rare",
                    "card_number_range": "204-220",
                    "name_contains": "VMAX",
                    "name_not_contains": "Alternate",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
                "card_pool_count": 11,
                "variant_pool_count": 11,
                "identifiability": "derived_from_card_number_range_and_name",
            },
            "gold secret rare": {
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
        "full art v": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Ultra Rare",
                "card_number_range": "166-198",
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
                "card_number_range": "199-203",
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
        "rainbow trainer": {
            "source": "rarity + card_number range",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "221-225",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "rainbow vmax": {
            "source": "rarity + card_number range + name",
            "card_filter": {
                "rarity": "Secret Rare",
                "card_number_range": "204-220",
                "name_contains": "VMAX",
                "name_not_contains": "Alternate",
            },
            "variant_filter": {"printing_type": "holo"},
            "include_reverse_variants": False,
        },
        "gold secret rare": {
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
            "Umbreon V (Full Art) (#179)": "full art v",
            "Umbreon V (Alternate Full Art) (#188)": "alternate art v",
            "Umbreon VMAX (#095)": "regular vmax",
            "Umbreon VMAX (#214, Secret Rare)": "rainbow vmax",
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
            (1 / 3)
            + (1 / 8.6)
            + (1 / 18.5)
            + ((1 / 82) * (22 / 27))
            + ((1 / 82) * (5 / 27))
            + (1 / 82)
            + (1 / 283)
            + ((1 / 99) * (5 / 28))
            + ((1 / 99) * (11 / 28))
            + ((1 / 99) * (12 / 28))
        ),
        "holo rare": 1 / 3,
        "regular v": 1 / 8.6,
        "regular vmax": 1 / 18.5,
        "full art v": (1 / 82) * (22 / 27),
        "full art trainer": (1 / 82) * (5 / 27),
        "alternate art v": 1 / 82,
        "alternate art vmax": 1 / 283,
        "rainbow trainer": (1 / 99) * (5 / 28),
        "rainbow vmax": (1 / 99) * (11 / 28),
        "gold secret rare": (1 / 99) * (12 / 28),
    }

    # Promoted to production runtime after strict DB-source validation.
    # Keep the *_DRAFT table and its audit ledger intact for traceability.
    RARE_SLOT_PROBABILITY = EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT

    EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT_AUDIT = {
        "status": "best_available_empirical_draft",
        "probability_model_status": "best_available_empirical_draft",
        "runtime_remains_disabled": True,
        "source_rows_used": {
            "Holo V": {
                "source_odds": "1/8.6",
                "normalized_bucket": "regular v",
                "probability": 1 / 8.6,
                "source_family": "cardzard_reddit_5000_pack",
            },
            "Holo VMAX": {
                "source_odds": "1/18.5",
                "normalized_bucket": "regular vmax",
                "probability": 1 / 18.5,
                "source_family": "cardzard_reddit_5000_pack",
            },
            "alternate art vmax": {
                "source_odds": "1/283",
                "normalized_bucket": "alternate art vmax",
                "probability": 1 / 283,
                "source_family": "cardzard_reddit_5000_pack",
            },
        },
        "source_rows_used_with_assumptions": {
            "holo_rare_secondary_directional": {
                "source_odds": "~1/3",
                "normalized_bucket": "holo rare",
                "probability": 1 / 3,
                "assumption": (
                    "Directional cross-source estimate used as best-available empirical draft for holo rare."
                ),
            },
            "high_rarity_row_1": {
                "source_odds": "1/82",
                "assumed_row_semantics": "full_art_umbrella",
                "normalization": {
                    "full art v": (1 / 82) * (22 / 27),
                    "full art trainer": (1 / 82) * (5 / 27),
                },
                "assumption": (
                    "When direct child rows are unavailable, parent-like high-rarity row is used and split by "
                    "non-overlapping mapped pool cardinality (22:5)."
                ),
            },
            "high_rarity_row_2": {
                "source_odds": "1/82",
                "assumed_row_semantics": "alternate_art_v",
                "normalized_bucket": "alternate art v",
                "probability": 1 / 82,
                "assumption": (
                    "Mapped as alternate art V in best-available draft due to source context mentioning separate "
                    "alternate art vmax row (1/283)."
                ),
            },
            "high_rarity_row_3": {
                "source_odds": "1/99",
                "assumed_row_semantics": "secret_non_alt_umbrella",
                "normalization": {
                    "rainbow trainer": (1 / 99) * (5 / 28),
                    "rainbow vmax": (1 / 99) * (11 / 28),
                    "gold secret rare": (1 / 99) * (12 / 28),
                },
                "assumption": (
                    "Parent-like secret umbrella split by mapped pool cardinality (5:11:12) because cleaner child "
                    "rows are not locally transcribed in machine-readable form."
                ),
            },
        },
        "source_rows_rejected": {
            "TCGplayer Umbreon VMAX alternate-art 0.05% (~1/2000)": "named_card_observation_rows_only",
        },
        "named_card_rows_excluded": {
            "Umbreon VMAX alternate-art 0.05% (~1/2000)": "named_card_observation_rows_only",
        },
        "parent_rows_used_with_assumptions": {
            "1/82_full_art_umbrella": {
                "policy_justification": "no cleaner direct child row available in local extracted text",
                "source_separates_premium_elsewhere": True,
            },
            "1/99_secret_non_alt_umbrella": {
                "policy_justification": "no cleaner direct child row available in local extracted text",
                "source_separates_premium_elsewhere": True,
            },
        },
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
                "status": "partially_transcribed_for_draft",
                "rows_transcribed": [
                    "Holo V: 1/8.6",
                    "Holo VMAX: 1/18.5",
                    "alternate art vmax: 1/283",
                    "high-rarity denominators: 1/82, 1/99, 1/82",
                ],
                "notes": (
                    "Rows are used as best-available empirical draft inputs with explicit assumptions where "
                    "exact row labels are not fully transcribed."
                ),
            },
            "reddit_pull_rate_discussions": {
                "status": "used_for_draft_context",
                "references": [
                    "https://reddit.com/r/PokemonTCG/comments/pf5scn/evolving_skies_pull_rate_data_from_5000_packs/",
                    "https://reddit.com/r/PokemonTCG/comments/1f35e2h/tcgplayers_evolving_skies_pull_rates_from_8000/",
                ],
                "rows_transcribed": [
                    "Holo V: 1/8.6",
                    "Holo VMAX: 1/18.5",
                    "alternate art vmax: 1/283",
                ],
                "notes": "Used as primary empirical context for draft modeling with explicit assumptions.",
            },
            "cardzard": {
                "status": "used_via_transcribed_public_commentary",
                "rows_transcribed": [
                    "regular v / Holo V: 1/8.6",
                    "regular vmax / Holo VMAX: 1/18.5",
                    "alternate art vmax: 1/283",
                    "high-rarity rows: 1/82, 1/99, 1/82",
                ],
                "notes": "Used as best-available empirical source family for draft table.",
            },
            "dripshop": {
                "status": "secondary_directional",
                "rows_transcribed": [
                    "holo around one in three packs",
                ],
                "notes": "Used only as assumption-backed directional support for holo rare in draft table.",
            },
        },
        "direct_non_overlapping_candidate_rows": {
            "regular v / Holo V": "1/8.6",
            "regular vmax / Holo VMAX": "1/18.5",
            "alternate art vmax": "1/283",
        },
        "parent_sanity_rows_only": {
            "high_rarity_denominator_row_a": "1/82",
            "high_rarity_denominator_row_b": "1/99",
            "high_rarity_denominator_row_c": "1/82",
        },
        "named_card_observation_rows_only": {
            "Umbreon VMAX alternate-art": "0.05% (~1/2000)",
        },
        "unusable_or_overlapping_rows": {
            "rows_kept_observation_only": [
                "TCGplayer named-card odds are never used as bucket weights",
            ],
        },
        "rare_slot_probability_readiness": {
            "can_construct_non_overlapping_source_backed_table": True,
            # rare is residual-capable: its probability = 1 - sum(all other rare-slot probabilities).
            # It does not need a direct source row.
            "rare_is_residual_capable": True,
            "rare_requires_direct_source_row": False,
            "missing_non_residual_outcomes": [],
            "high_rarity_overlap_status": "resolved_for_draft_via_assumption_documentation",
            "parent_rows_excluded": False,
            "parent_rows_used_with_assumptions": True,
            "named_card_rows_excluded": True,
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
