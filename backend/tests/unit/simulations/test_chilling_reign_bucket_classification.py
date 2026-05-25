from pathlib import Path

import pytest

from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig


def test_chilling_reign_bucket_counts_match_project_611_expected_counts():
    outcomes = SetChillingReignConfig.CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT["outcomes"]

    expected = {
        "rare": 23,
        "holo rare": 24,
        "regular v": 15,
        "regular vmax": 8,
        "full art v": 16,
        "full art trainer": 13,
        "alternate art v": 10,
        "alternate art vmax": 3,
        "rainbow trainer": 12,
        "rainbow vmax": 8,
        "gold secret rare": 12,
    }

    actual = {bucket: details["variant_pool_count"] for bucket, details in outcomes.items()}
    assert actual == expected

    total = sum(actual.values())
    assert total == 144

    compact_audit = SetChillingReignConfig.CHILLING_REIGN_BUCKET_CLASSIFICATION_AUDIT
    assert compact_audit["eligible_non_reverse_rare_family_variants"] == total
    assert compact_audit["mapped_variants"] == total


def test_chilling_reign_rare_is_residual_capable_and_not_a_direct_source_blocker():
    coverage = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_COVERAGE_AUDIT

    assert coverage["rare_is_residual_capable"] is True
    assert coverage["rare_requires_direct_source_row"] is False

    missing_non_residual = set(coverage["missing_non_residual_outcomes_blocking_rare_slot_probability"])
    assert "rare" not in missing_non_residual
    assert {"holo rare", "regular v", "regular vmax"}.issubset(missing_non_residual)


def test_chilling_reign_direct_parent_named_row_classification_is_stable():
    mapping = SetChillingReignConfig.CHILLING_REIGN_SOURCE_BUCKET_MAPPING
    outcome_buckets = set(SetChillingReignConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())

    direct_rows = {row: details for row, details in mapping.items() if details["used_as_direct_outcome"]}
    parent_rows = ["VMAX", "Full Art", "Rainbow"]
    named_rows = [
        "Gold Snorlax",
        "Ice Calyrex VMAX Alt",
        "Shadow Calyrex VMAX Alt",
        "Blaziken VMAX Alt",
    ]

    assert set(direct_rows.keys()) == {
        "Full Art V",
        "Full Art Trainer",
        "Full Art Alt",
        "VMAX Alt",
        "Rainbow Trainer",
        "Rainbow VMAX",
        "Gold",
    }
    assert {details["normalized_bucket"] for details in direct_rows.values()}.issubset(outcome_buckets)

    for row in parent_rows:
        assert mapping[row]["used_as_direct_outcome"] is False

    for row in named_rows:
        assert mapping[row]["used_as_direct_outcome"] is False
        assert mapping[row]["normalized_bucket"] == "named-card-observation"


def test_chilling_reign_outcome_mapping_excludes_reverse_holo_variants():
    outcomes = SetChillingReignConfig.CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT["outcomes"]

    for outcome_name, details in outcomes.items():
        assert details["include_reverse_variants"] is False, outcome_name
        assert details["variant_filter"]["printing_type"] in {"holo", "non-holo"}
        assert details["variant_filter"]["printing_type"] != "reverse-holo"


def test_chilling_reign_production_probability_table_present_and_runtime_enabled_intentionally():
    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY")
    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert SetChillingReignConfig.RARE_SLOT_PROBABILITY == SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT


def test_chilling_reign_draft_probability_table_matches_mapping_and_sums_to_one():
    draft_table = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT
    mapping_keys = set(SetChillingReignConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())

    assert set(draft_table.keys()) == mapping_keys
    assert draft_table["rare"] >= 0.0
    assert sum(draft_table.values()) == pytest.approx(1.0)


def test_chilling_reign_draft_audit_documents_assumption_rows_and_named_card_exclusions():
    audit = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT

    assert audit["probability_model_status"] == "best_available_empirical_draft"
    assert audit["runtime_remains_disabled"] is True
    assert audit["source_rows_used_with_assumptions"]
    assert audit["parent_rows_used_with_assumptions"] == {}
    assert "Gold Snorlax" in audit["named_card_rows_excluded"]
    assert audit["named_card_rows_excluded"]["Gold Snorlax"] == "named_card_observation_rows_only"
    assert audit["residual_rare_probability"] == pytest.approx(
        SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT["rare"]
    )


def test_chilling_reign_bucket_ledger_artifact_exists_and_documents_residual_rare():
    ledger = Path("backend/docs/audits/CHILLING_REIGN_BUCKET_CLASSIFICATION_LEDGER.md")
    assert ledger.exists()

    content = ledger.read_text(encoding="utf-8")
    assert "eligible_non_reverse_rare_family_variants" in content
    assert "**144**" in content
    assert "residual-capable" in content
