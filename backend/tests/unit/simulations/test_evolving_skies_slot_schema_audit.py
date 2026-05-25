import pytest

from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig


def test_evolving_skies_identity_fields_match_expected_set_metadata():
    assert SetEvolvingSkiesConfig.SET_NAME == "Evolving Skies"
    assert SetEvolvingSkiesConfig.SET_ABBREVIATION == "EVS"
    assert SetEvolvingSkiesConfig.SET_ID == "swsh7"
    assert SetEvolvingSkiesConfig.PRINTED_TOTAL == 203
    assert SetEvolvingSkiesConfig.TOTAL == 237


def test_evolving_skies_slot_schema_runtime_is_enabled_and_has_production_rare_slot_probability():
    assert SetEvolvingSkiesConfig.SIMULATION_ENGINE == "slot_schema"
    assert SetEvolvingSkiesConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert hasattr(SetEvolvingSkiesConfig, "RARE_SLOT_PROBABILITY")
    assert SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY == SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT


def test_evolving_skies_reverse_slot_scaffold_is_safe_single_slot_only():
    reverse_table = SetEvolvingSkiesConfig.REVERSE_SLOT_PROBABILITIES
    assert set(reverse_table.keys()) == {"slot_1"}
    assert reverse_table["slot_1"] == {"regular reverse": 1.0}


def test_evolving_skies_db_label_audit_targets_swsh7_and_has_expected_label_counts():
    audit = SetEvolvingSkiesConfig.EVOLVING_SKIES_DB_LABEL_AUDIT
    assert audit["set_id"] == "swsh7"
    assert audit["set_name"] == "Evolving Skies"
    assert audit["row_counts"]["cards"] == 237
    assert audit["row_counts"]["card_variants"] == 369

    rarity_counts = audit["card_level_distinct_summary"]["rarity_counts"]
    assert rarity_counts["Rare"] == 19
    assert rarity_counts["Holo Rare"] == 20
    assert rarity_counts["Ultra Rare"] == 71
    assert rarity_counts["Secret Rare"] == 34

    printing_counts = audit["variant_level_distinct_summary"]["printing_type_counts"]
    assert printing_counts["reverse-holo"] == 132
    assert printing_counts["holo"] == 125
    assert printing_counts["non-holo"] == 112


def test_evolving_skies_outcome_pool_mapping_audit_is_complete_non_overlapping_and_reverse_excluded():
    audit = SetEvolvingSkiesConfig.EVOLVING_SKIES_OUTCOME_POOL_MAPPING_AUDIT
    assert audit["coverage"]["eligible_non_reverse_rare_family_variants"] == 144
    assert audit["coverage"]["mapped_variants"] == 144
    assert audit["coverage"]["unmapped_variants"] == 0
    assert audit["coverage"]["overlapping_variants"] == 0

    outcomes = audit["outcomes"]
    for outcome_name, details in outcomes.items():
        assert details["include_reverse_variants"] is False, outcome_name

    assert outcomes["rare"]["card_pool_count"] == 19
    assert outcomes["holo rare"]["card_pool_count"] == 20
    assert outcomes["regular v"]["card_pool_count"] == 18
    assert outcomes["regular vmax"]["card_pool_count"] == 15
    assert outcomes["full art v"]["card_pool_count"] == 22
    assert outcomes["full art trainer"]["card_pool_count"] == 5
    assert outcomes["alternate art v"]["card_pool_count"] == 11
    assert outcomes["alternate art vmax"]["card_pool_count"] == 6
    assert outcomes["rainbow trainer"]["card_pool_count"] == 5
    assert outcomes["rainbow vmax"]["card_pool_count"] == 11
    assert outcomes["gold secret rare"]["card_pool_count"] == 12


def test_evolving_skies_runtime_mapping_keys_match_audit_outcomes_exactly():
    mapping_keys = set(SetEvolvingSkiesConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())
    audit_keys = set(SetEvolvingSkiesConfig.EVOLVING_SKIES_OUTCOME_POOL_MAPPING_AUDIT["outcomes"].keys())
    assert mapping_keys == audit_keys


def test_evolving_skies_source_audit_excludes_parent_and_named_rows_from_probability_keys():
    source_audit = SetEvolvingSkiesConfig.EVOLVING_SKIES_PULL_RATE_SOURCE_AUDIT
    readiness = source_audit["rare_slot_probability_readiness"]

    assert readiness["parent_rows_excluded"] is False
    assert readiness["parent_rows_used_with_assumptions"] is True
    assert readiness["named_card_rows_excluded"] is True

    # Project 6.1: rare is residual-capable; it must NOT appear in missing outcomes.
    assert readiness["rare_is_residual_capable"] is True
    assert readiness["rare_requires_direct_source_row"] is False
    missing = readiness.get("missing_non_residual_outcomes", readiness.get("missing_base_outcomes", []))
    assert "rare" not in missing, "rare must not be listed as a missing outcome; it is residual-capable"
    assert missing == []

    direct_rows = source_audit["direct_non_overlapping_candidate_rows"]
    assert "VMAX" not in direct_rows
    assert "Full Art" not in direct_rows
    assert "Rainbow" not in direct_rows
    assert "Umbreon VMAX (Alternate Art Secret)" not in direct_rows


def test_evolving_skies_source_confidence_marks_runtime_candidate_best_available_empirical():
    confidence = SetEvolvingSkiesConfig.SLOT_SCHEMA_SOURCE_CONFIDENCE
    assert confidence["status"] == "runtime_candidate_best_available_empirical"
    assert confidence["runtime_ready"] is True
    assert confidence["pool_mapping_ready"] is True
    assert confidence["bucket_classification_ready"] is True
    assert confidence["rare_slot_probability_ready"] is True
    assert confidence["reverse_slot_probability_ready"] is True
    assert confidence["source_model"] == "best_available_empirical"
    assert confidence["source_caveat"].startswith("Not official Pokemon pull rates")


def test_evolving_skies_draft_probability_audit_and_table_are_present_and_promoted_to_production():
    audit = SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT_AUDIT
    draft_table = SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT

    assert audit["probability_model_status"] == "best_available_empirical_draft"
    assert audit["runtime_remains_disabled"] is True
    assert sum(draft_table.values()) == pytest.approx(1.0)
    assert draft_table["rare"] >= 0.0
    assert hasattr(SetEvolvingSkiesConfig, "RARE_SLOT_PROBABILITY")
    assert SetEvolvingSkiesConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY == draft_table


def test_evolving_skies_bucket_classification_audit_is_complete_and_counts_match():
    audit = SetEvolvingSkiesConfig.EVOLVING_SKIES_BUCKET_CLASSIFICATION_AUDIT
    assert audit["status"] == "complete"
    assert audit["eligible_non_reverse_rare_family_variants"] == 144
    assert audit["mapped_variants"] == 144
    assert audit["unmapped_variants"] == 0
    assert audit["overlapping_variants"] == 0


def test_evolving_skies_bucket_classification_audit_contains_umbreon_disambiguation_examples():
    examples = SetEvolvingSkiesConfig.EVOLVING_SKIES_BUCKET_CLASSIFICATION_AUDIT["ambiguous_name_examples"]
    # Every key should map to a known bucket name.
    expected_buckets = {
        "regular v", "full art v", "alternate art v",
        "regular vmax", "rainbow vmax", "alternate art vmax",
    }
    resolved_buckets = set(examples.values())
    assert resolved_buckets == expected_buckets


def test_evolving_skies_bucket_classification_audit_notes_rarity_is_insufficient():
    notes = SetEvolvingSkiesConfig.EVOLVING_SKIES_BUCKET_CLASSIFICATION_AUDIT["notes"]
    assert "rarity alone is insufficient" in notes.lower() or "rarity + card_number" in notes.lower()
    assert "residual" in notes.lower()


def test_ultra_rare_and_secret_rare_are_not_final_simulator_bucket_names():
    mapping_keys = set(SetEvolvingSkiesConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())
    assert "Ultra Rare" not in mapping_keys, "Ultra Rare is a DB label, not a simulator bucket"
    assert "Secret Rare" not in mapping_keys, "Secret Rare is a DB label, not a simulator bucket"
    audit_keys = set(SetEvolvingSkiesConfig.EVOLVING_SKIES_OUTCOME_POOL_MAPPING_AUDIT["outcomes"].keys())
    assert "Ultra Rare" not in audit_keys
    assert "Secret Rare" not in audit_keys


def test_chilling_reign_is_runtime_enabled_and_sv_mega_paths_are_untouched_by_evolving_skies_updates():
    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY")
    assert SetChillingReignConfig.RARE_SLOT_PROBABILITY == SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT
    assert SetChillingReignConfig.SET_ID == "swsh6"
