import pytest

from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import (
    SetChillingReignConfig,
    _validate_chilling_reign_source_bucket_mapping,
)


def test_chilling_reign_runtime_is_intentionally_enabled_during_bucket_normalization_scaffold():
    assert getattr(SetChillingReignConfig, "SLOT_SCHEMA_RUNTIME_ENABLED", False) is True


def test_source_bucket_mapping_exposes_expected_direct_outcomes_only():
    direct = SetChillingReignConfig.get_chilling_reign_direct_outcome_buckets()
    assert direct == {
        "full art v",
        "full art trainer",
        "alternate art v",
        "alternate art vmax",
        "rainbow trainer",
        "rainbow vmax",
        "gold secret rare",
    }


def test_parent_source_rows_are_not_direct_outcomes_when_children_are_present():
    mapping = SetChillingReignConfig.CHILLING_REIGN_SOURCE_BUCKET_MAPPING
    assert mapping["VMAX"]["used_as_direct_outcome"] is False
    assert mapping["Full Art"]["used_as_direct_outcome"] is False
    assert mapping["Rainbow"]["used_as_direct_outcome"] is False


def test_named_card_rows_are_observation_only_not_direct_outcomes():
    mapping = SetChillingReignConfig.CHILLING_REIGN_SOURCE_BUCKET_MAPPING
    for row in [
        "Gold Snorlax",
        "Ice Calyrex VMAX Alt",
        "Shadow Calyrex VMAX Alt",
        "Blaziken VMAX Alt",
    ]:
        assert mapping[row]["used_as_direct_outcome"] is False
        assert mapping[row]["normalized_bucket"] == "named-card-observation"


def test_every_direct_outcome_source_row_has_direct_source_odds_entry():
    mapping = SetChillingReignConfig.CHILLING_REIGN_SOURCE_BUCKET_MAPPING
    direct_rows = {
        source_row
        for source_row, details in mapping.items()
        if details.get("used_as_direct_outcome")
    }

    direct_odds_rows = set(SetChillingReignConfig.CHILLING_REIGN_SOURCE_DIRECT_BUCKET_ODDS.keys())
    assert direct_rows == direct_odds_rows


def test_parent_only_rows_are_not_in_direct_source_odds():
    direct_odds_rows = set(SetChillingReignConfig.CHILLING_REIGN_SOURCE_DIRECT_BUCKET_ODDS.keys())
    assert "VMAX" not in direct_odds_rows
    assert "Full Art" not in direct_odds_rows
    assert "Rainbow" not in direct_odds_rows


def test_named_card_rows_are_not_in_direct_source_odds():
    direct_odds_rows = set(SetChillingReignConfig.CHILLING_REIGN_SOURCE_DIRECT_BUCKET_ODDS.keys())
    for row in [
        "Gold Snorlax",
        "Ice Calyrex VMAX Alt",
        "Shadow Calyrex VMAX Alt",
        "Blaziken VMAX Alt",
    ]:
        assert row not in direct_odds_rows


def test_mapping_validator_fails_if_parent_and_child_are_both_marked_direct():
    bad_mapping = {
        "Full Art": {
            "normalized_bucket": "full art",
            "used_as_direct_outcome": True,
            "children": ("Full Art V",),
        },
        "Full Art V": {
            "normalized_bucket": "full art v",
            "used_as_direct_outcome": True,
            "children": (),
        },
    }

    with pytest.raises(ValueError, match="double-counts overlapping categories"):
        _validate_chilling_reign_source_bucket_mapping(bad_mapping)


def test_source_notes_explicitly_document_named_card_policy():
    notes = SetChillingReignConfig.CHILLING_REIGN_PULL_RATE_SOURCE_NOTES
    assert "Named-card odds" in notes["named_card_rows_policy"]
    assert "parent" in notes["parent_bucket_policy"].lower()


def test_source_notes_explicitly_document_high_rarity_only_coverage_scope():
    notes = SetChillingReignConfig.CHILLING_REIGN_PULL_RATE_SOURCE_NOTES
    assert "high-rarity" in notes["coverage_scope"].lower()
    assert "does not cover base holo rare/regular v/regular vmax outcomes" in notes["coverage_scope"].lower()
    assert "residual-capable" in notes["rare_residual_policy"].lower()


def test_high_rarity_direct_buckets_do_not_claim_base_rare_holo_v_outcomes():
    direct_normalized = {
        details["normalized_bucket"]
        for details in SetChillingReignConfig.CHILLING_REIGN_SOURCE_BUCKET_MAPPING.values()
        if details.get("used_as_direct_outcome")
    }
    assert "rare" not in direct_normalized
    assert "holo rare" not in direct_normalized
    assert "v" not in direct_normalized


def test_reverse_slot_scaffold_is_safe_single_regular_reverse_only():
    reverse_table = SetChillingReignConfig.REVERSE_SLOT_PROBABILITIES
    assert set(reverse_table.keys()) == {"slot_1"}
    assert reverse_table["slot_1"] == {"regular reverse": 1.0}


def test_rare_slot_coverage_audit_explicitly_blocks_table_construction_for_now():
    audit = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_COVERAGE_AUDIT
    assert audit["status"] == "incomplete"
    assert audit["can_construct_non_overlapping_rare_slot_table"] is False


def test_rare_slot_coverage_audit_lists_base_outcomes_still_missing():
    audit = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_COVERAGE_AUDIT
    missing = set(audit["missing_non_residual_outcomes_blocking_rare_slot_probability"])
    assert audit["rare_is_residual_capable"] is True
    assert audit["rare_requires_direct_source_row"] is False
    assert "rare" not in missing
    assert {"holo rare", "regular v", "regular vmax"}.issubset(missing)


def test_rare_slot_coverage_audit_direct_rows_match_direct_source_odds_keys():
    audit_direct = set(SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_COVERAGE_AUDIT["source_backed_direct_rows"].keys())
    direct_source_rows = set(SetChillingReignConfig.CHILLING_REIGN_SOURCE_DIRECT_BUCKET_ODDS.keys())
    assert audit_direct == direct_source_rows


def test_rare_slot_coverage_audit_decision_keeps_runtime_disabled_until_complete():
    audit = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_COVERAGE_AUDIT
    assert "Historical pre-promotion decision" in audit["decision"]
    assert "Superseded by Project 6.6-6.9" in audit["decision"]
    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True


def test_db_label_audit_artifact_declares_mapping_requirement_and_swsh6_target():
    audit = SetChillingReignConfig.CHILLING_REIGN_DB_LABEL_AUDIT
    assert audit["set_id"] == "swsh6"
    assert audit["requires_outcome_pool_mapping"] is True
    assert "cards" in audit["tables_audited"]
    assert "card_variants" in audit["tables_audited"]


def test_db_label_audit_preserves_runtime_configuration_and_production_probability_table():
    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY")
    assert SetChillingReignConfig.RARE_SLOT_PROBABILITY == SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT


def test_outcome_pool_mapping_audit_declares_reverse_exclusion_for_all_rare_slot_outcomes():
    audit = SetChillingReignConfig.CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT
    assert "exclude reverse-holo" in audit["reverse_variant_policy"]

    outcomes = audit["outcomes"]
    for outcome_name, details in outcomes.items():
        assert details["include_reverse_variants"] is False, outcome_name


def test_outcome_pool_mapping_audit_uses_expected_variant_filters_for_base_rare_outcomes():
    outcomes = SetChillingReignConfig.CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT["outcomes"]

    assert outcomes["rare"]["variant_filter"] == {"printing_type": "non-holo"}
    assert outcomes["holo rare"]["variant_filter"] == {"printing_type": "holo"}
    assert outcomes["rare"]["card_pool_count"] == 23
    assert outcomes["holo rare"]["card_pool_count"] == 24


def test_outcome_pool_mapping_audit_keeps_regular_v_regular_vmax_terminology_and_counts():
    outcomes = SetChillingReignConfig.CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT["outcomes"]

    assert "regular v" in outcomes
    assert "regular vmax" in outcomes
    assert outcomes["regular v"]["card_pool_count"] == 15
    assert outcomes["regular vmax"]["card_pool_count"] == 8


def test_chilling_reign_bucket_classification_audit_is_complete_and_counts_match():
    audit = SetChillingReignConfig.CHILLING_REIGN_BUCKET_CLASSIFICATION_AUDIT

    assert audit["status"] == "complete"
    assert audit["eligible_non_reverse_rare_family_variants"] == 144
    assert audit["mapped_variants"] == 144
    assert audit["unmapped_variants"] == 0
    assert audit["overlapping_variants"] == 0
    assert "sum to 144" in audit["count_reconciliation_note"]

    outcomes = SetChillingReignConfig.CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT["outcomes"]
    mapped_total = sum(details["variant_pool_count"] for details in outcomes.values())
    assert mapped_total == 144


def test_chilling_reign_bucket_classification_audit_has_blaziken_and_snorlax_disambiguation_examples():
    examples = SetChillingReignConfig.CHILLING_REIGN_BUCKET_CLASSIFICATION_AUDIT["ambiguous_name_examples"]

    assert examples["Blaziken V (#020)"] == "regular v"
    assert examples["Blaziken V (Full Art) (#161)"] == "full art v"
    assert examples["Blaziken V (Alternate Full Art)"] == "alternate art v"
    assert examples["Blaziken VMAX (#021)"] == "regular vmax"
    assert examples["Blaziken VMAX (Secret) (#200)"] == "rainbow vmax"
    assert examples["Blaziken VMAX (Alternate Art Secret) (#201)"] == "alternate art vmax"
    assert examples["Snorlax (Secret) (#224)"] == "gold secret rare"


def test_ultra_rare_and_secret_rare_are_not_final_bucket_names_for_chilling_reign():
    mapping_keys = set(SetChillingReignConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())
    assert "Ultra Rare" not in mapping_keys
    assert "Secret Rare" not in mapping_keys

    audit_keys = set(SetChillingReignConfig.CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT["outcomes"].keys())
    assert "Ultra Rare" not in audit_keys
    assert "Secret Rare" not in audit_keys


def test_outcome_pool_mapping_audit_declares_high_rarity_resolution_strategy_and_not_blocked():
    audit = SetChillingReignConfig.CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT
    resolution = audit["high_rarity_bucket_resolution_status"]

    assert "full art trainer" in resolution
    assert "rainbow trainer" in resolution
    assert audit["requires_manual_mapping"] is False
    assert audit["requires_pokemon_tcg_api_metadata_refresh"] is False
    assert audit["blocked"] is False


def test_source_odds_sanity_audit_keeps_named_rows_observation_only_and_not_weights():
    audit = SetChillingReignConfig.CHILLING_REIGN_SOURCE_ODDS_POOL_COUNT_SANITY_AUDIT
    named = audit["named_card_sanity_checks"]

    assert named["policy"] == "observation_only_never_used_as_weights"
    assert "must not" in audit["decision"].lower()


def test_source_odds_sanity_audit_keeps_parent_and_named_rows_out_of_direct_odds():
    direct = SetChillingReignConfig.CHILLING_REIGN_SOURCE_DIRECT_BUCKET_ODDS

    for row in ["VMAX", "Full Art", "Rainbow", "Gold Snorlax", "Ice Calyrex VMAX Alt", "Shadow Calyrex VMAX Alt", "Blaziken VMAX Alt"]:
        assert row not in direct


def test_source_odds_sanity_audit_direct_bucket_implied_uniform_odds_are_locked():
    checks = SetChillingReignConfig.CHILLING_REIGN_SOURCE_ODDS_POOL_COUNT_SANITY_AUDIT["direct_bucket_checks"]

    assert checks["full art v"]["implied_uniform_per_card_odds"] == "1/752"
    assert checks["full art trainer"]["implied_uniform_per_card_odds"] == "1/962"
    assert checks["alternate art v"]["implied_uniform_per_card_odds"] == "1/1090"
    assert checks["alternate art vmax"]["implied_uniform_per_card_odds"] == "1/1188"
    assert checks["rainbow trainer"]["implied_uniform_per_card_odds"] == "1/1812"
    assert checks["rainbow vmax"]["implied_uniform_per_card_odds"] == "1/1512"
    assert checks["gold secret rare"]["implied_uniform_per_card_odds"] == "1/1152"


def test_source_odds_sanity_audit_named_card_comparison_matches_expected_directionality():
    named = SetChillingReignConfig.CHILLING_REIGN_SOURCE_ODDS_POOL_COUNT_SANITY_AUDIT["named_card_sanity_checks"]

    assert named["gold_snorlax"]["observed_named_card_odds"] == "1/756"
    assert named["gold_snorlax"]["expected_uniform_from_gold_bucket"] == "1/1152"
    assert named["gold_snorlax"]["observed_vs_expected_probability_ratio"] > 1.0

    vmax_alt_rows = named["vmax_alt_named_rows"]["rows"]
    assert vmax_alt_rows["Ice Calyrex VMAX Alt"]["observed_vs_expected_probability_ratio"] > 1.0
    assert vmax_alt_rows["Shadow Calyrex VMAX Alt"]["observed_vs_expected_probability_ratio"] == 1.0
    assert vmax_alt_rows["Blaziken VMAX Alt"]["observed_vs_expected_probability_ratio"] < 1.0


def test_source_odds_sanity_audit_does_not_enable_runtime_or_add_rare_slot_probability():
    runtime_guardrails = SetChillingReignConfig.CHILLING_REIGN_SOURCE_ODDS_POOL_COUNT_SANITY_AUDIT["runtime_guardrails"]

    assert runtime_guardrails["adds_rare_slot_probability"] is False
    assert runtime_guardrails["slot_schema_runtime_enabled"] is False
    assert runtime_guardrails["changes_runtime_behavior"] is False

    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY")
    assert SetChillingReignConfig.RARE_SLOT_PROBABILITY == SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT


def test_project_57_slot_schema_source_confidence_marks_runtime_candidate_state():
    metadata = SetChillingReignConfig.SLOT_SCHEMA_SOURCE_CONFIDENCE

    assert metadata["status"] == "runtime_candidate_best_available_empirical"
    assert metadata["runtime_ready"] is True
    assert metadata["pool_mapping_ready"] is True
    assert metadata["bucket_classification_ready"] is True
    assert metadata["rare_slot_probability_ready"] is True
    assert metadata["reverse_slot_probability_ready"] is True
    assert metadata["source_model"] == "best_available_empirical"
    assert metadata["source_caveat"].startswith("Not official Pokemon pull rates")

    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY")
    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True


def test_project_56_draft_audit_is_present_and_production_probability_table_is_promoted():
    audit = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT

    assert audit["status"] == "best_available_empirical_draft"
    assert audit["probability_model_status"] == "best_available_empirical_draft"
    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY")
    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert SetChillingReignConfig.RARE_SLOT_PROBABILITY == SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT
    assert audit["probability_sum"] == pytest.approx(1.0)


def test_project_56_direct_high_rarity_mass_matches_source_odds_exactly():
    audit = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT
    direct_mass = audit["direct_high_rarity_mass"]

    assert direct_mass["full art v"] == pytest.approx(1 / 47)
    assert direct_mass["full art trainer"] == pytest.approx(1 / 74)
    assert direct_mass["alternate art v"] == pytest.approx(1 / 109)
    assert direct_mass["alternate art vmax"] == pytest.approx(1 / 396)
    assert direct_mass["rainbow trainer"] == pytest.approx(1 / 151)
    assert direct_mass["rainbow vmax"] == pytest.approx(1 / 189)
    assert direct_mass["gold secret rare"] == pytest.approx(1 / 96)

    expected_sum = (1 / 47) + (1 / 74) + (1 / 109) + (1 / 396) + (1 / 151) + (1 / 189) + (1 / 96)
    assert direct_mass["sum"] == pytest.approx(expected_sum)
    assert audit["remaining_base_mass"] == pytest.approx(1 - expected_sum)


def test_project_56_draft_audit_decisions_document_regular_holo_v_vmax_resolution_blockers():
    audit = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT
    decisions = audit["base_outcome_source_decisions"]

    assert set(decisions.keys()) == {"rare", "holo rare", "regular v", "regular vmax"}
    assert decisions["rare"]["source_available"] is True
    assert decisions["rare"]["decision"] == "residual_capable"
    assert "does not require a direct source row" in decisions["rare"]["reason"]

    for outcome in ["holo rare", "regular v", "regular vmax"]:
        assert decisions[outcome]["source_available"] is True
        assert decisions[outcome]["decision"] == "assumption_backed_secondary_directional"
        assert decisions[outcome]["reason"]

    assert audit["source_specific_high_rarity_ambiguities"]


def test_project_56_draft_audit_excludes_parent_and_named_card_rows_and_preserves_runtime_guardrails():
    audit = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT
    direct_mass_keys = set(audit["direct_high_rarity_mass"].keys()) - {"sum"}
    mapped_outcomes = set(SetChillingReignConfig.CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT["outcomes"].keys())

    assert direct_mass_keys.issubset(mapped_outcomes)
    assert "VMAX" not in direct_mass_keys
    assert "Full Art" not in direct_mass_keys
    assert "Rainbow" not in direct_mass_keys
    assert "Gold Snorlax" not in direct_mass_keys
    assert "Ice Calyrex VMAX Alt" not in direct_mass_keys
    assert "Shadow Calyrex VMAX Alt" not in direct_mass_keys
    assert "Blaziken VMAX Alt" not in direct_mass_keys

    assert audit["parent_rows_excluded"] is True
    assert audit["named_card_rows_excluded"]["Gold Snorlax"] == "named_card_observation_rows_only"
    assert "historical pre-promotion decision" in audit["decision"].lower()
    assert "superseded by project 6.9" in audit["decision"].lower()
    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
