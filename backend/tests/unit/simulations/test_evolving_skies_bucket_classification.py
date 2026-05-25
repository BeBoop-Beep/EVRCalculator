"""
Project 6.1 — Evolving Skies Bucket Classification Tests.

Validates:
- SLOT_SCHEMA_OUTCOME_POOL_MAPPING keys match audit outcomes (no drift).
- All 144 eligible non-reverse rare-family variants are accounted for in bucket counts.
- No reverse-holo rows enter rare-slot buckets.
- No mapped pools overlap on the Umbreon name family.
- No mapped rare-family variants are missing from the classification.
- Ultra Rare / Secret Rare are not treated as final bucket names.
- Rare is residual-capable (no direct source row required).
- Name-disambiguation tests using tiny fake DataFrame rows confirm each bucket
  resolves the correct Umbreon family variant.
"""
import pandas as pd
import pytest
from typing import Dict, List

from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.simulations.slotSchemaOutcomeResolver import apply_slot_schema_outcome_pool_mapping


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _umbreon_family_df() -> pd.DataFrame:
    """Minimal DataFrame representing the six Umbreon rare-family variants.

    Each row is constructed to match exactly one SLOT_SCHEMA_OUTCOME_POOL_MAPPING bucket.
    Card numbers are illustrative and consistent with EVS structure:
      - regular V / VMAX: numbered within printed set (≤ 203)
      - full art V: numbered in 166–198 range
      - alternate full art V: Ultra Rare with '(Alternate Full Art)' in name
      - rainbow VMAX: Secret Rare, numbered 204–220
      - alternate art VMAX: Secret Rare, name contains 'Alternate Art Secret'
    """
    return pd.DataFrame([
        {
            "name": "Umbreon V",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "94",
        },
        {
            "name": "Umbreon V (Full Art)",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "179",
        },
        {
            "name": "Umbreon V (Alternate Full Art)",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "188",
        },
        {
            "name": "Umbreon VMAX",
            "rarity": "Ultra Rare",
            "printing_type": "holo",
            "card_number": "95",
        },
        {
            "name": "Umbreon VMAX",
            "rarity": "Secret Rare",
            "printing_type": "holo",
            "card_number": "214",
        },
        {
            "name": "Umbreon VMAX Alternate Art Secret",
            "rarity": "Secret Rare",
            "printing_type": "holo",
            "card_number": "215",
        },
    ])


def _gold_card_row() -> pd.DataFrame:
    """A single gold secret rare row (Raihan, card #234)."""
    return pd.DataFrame([
        {
            "name": "Raihan",
            "rarity": "Secret Rare",
            "printing_type": "holo",
            "card_number": "234",
        },
    ])


def _reverse_holo_rare_row() -> pd.DataFrame:
    """A reverse-holo Rare row that must NOT enter rare-slot rare bucket."""
    return pd.DataFrame([
        {
            "name": "Applin",
            "rarity": "Rare",
            "printing_type": "reverse-holo",
            "card_number": "1",
        },
    ])


# ---------------------------------------------------------------------------
# Structural contract tests
# ---------------------------------------------------------------------------

def test_mapping_keys_match_audit_outcomes_exactly():
    """SLOT_SCHEMA_OUTCOME_POOL_MAPPING keys must equal EVOLVING_SKIES_OUTCOME_POOL_MAPPING_AUDIT keys."""
    mapping_keys = set(SetEvolvingSkiesConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())
    audit_keys = set(SetEvolvingSkiesConfig.EVOLVING_SKIES_OUTCOME_POOL_MAPPING_AUDIT["outcomes"].keys())
    assert mapping_keys == audit_keys, (
        f"Mapping drift detected.\n"
        f"  In mapping only: {mapping_keys - audit_keys}\n"
        f"  In audit only:   {audit_keys - mapping_keys}"
    )


def test_all_144_eligible_non_reverse_variants_accounted_for_in_bucket_counts():
    """Bucket variant counts in the audit must sum to 144."""
    outcomes = SetEvolvingSkiesConfig.EVOLVING_SKIES_OUTCOME_POOL_MAPPING_AUDIT["outcomes"]
    total = sum(outcome["variant_pool_count"] for outcome in outcomes.values())
    assert total == 144, f"Expected 144, got {total}"


def test_no_unmapped_and_no_overlapping_variants():
    coverage = SetEvolvingSkiesConfig.EVOLVING_SKIES_OUTCOME_POOL_MAPPING_AUDIT["coverage"]
    assert coverage["unmapped_variants"] == 0
    assert coverage["overlapping_variants"] == 0


def test_all_bucket_outcomes_exclude_reverse_holo_variants():
    """Every outcome in the mapping must set include_reverse_variants = False."""
    mapping = SetEvolvingSkiesConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING
    for bucket, details in mapping.items():
        assert details.get("include_reverse_variants") is False, (
            f"Bucket {bucket!r} must have include_reverse_variants=False"
        )


def test_ultra_rare_is_not_a_final_bucket_name():
    """Ultra Rare is a DB label, not a simulator bucket.  It must not appear as a mapping key."""
    mapping_keys = set(SetEvolvingSkiesConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())
    assert "Ultra Rare" not in mapping_keys


def test_secret_rare_is_not_a_final_bucket_name():
    """Secret Rare is a DB label, not a simulator bucket.  It must not appear as a mapping key."""
    mapping_keys = set(SetEvolvingSkiesConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())
    assert "Secret Rare" not in mapping_keys


def test_rare_is_documented_as_residual_capable():
    readiness = SetEvolvingSkiesConfig.EVOLVING_SKIES_PULL_RATE_SOURCE_AUDIT["rare_slot_probability_readiness"]
    assert readiness["rare_is_residual_capable"] is True
    assert readiness["rare_requires_direct_source_row"] is False
    assert readiness["can_construct_non_overlapping_source_backed_table"] is True


def test_rare_not_in_non_residual_missing_outcomes():
    readiness = SetEvolvingSkiesConfig.EVOLVING_SKIES_PULL_RATE_SOURCE_AUDIT["rare_slot_probability_readiness"]
    missing = readiness.get("missing_non_residual_outcomes", readiness.get("missing_base_outcomes", []))
    assert "rare" not in missing, "rare is residual; it should not be listed as a missing outcome"


def test_rare_not_in_blocking_reasons():
    confidence = SetEvolvingSkiesConfig.SLOT_SCHEMA_SOURCE_CONFIDENCE
    reasons = confidence["blocking_reasons"]
    assert "missing_non_overlapping_source_backed_probabilities_for_rare" not in reasons, (
        "rare is residual-capable; its blocking reason must be removed"
    )
    assert reasons == []
    assert confidence["status"] == "runtime_candidate_best_available_empirical"
    assert confidence["runtime_ready"] is True


def test_evolving_skies_draft_probability_table_matches_mapping_keys_and_sums_to_one():
    draft_table = SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT
    mapping_keys = set(SetEvolvingSkiesConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())

    assert set(draft_table.keys()) == mapping_keys
    assert draft_table["rare"] >= 0.0
    assert sum(draft_table.values()) == pytest.approx(1.0)


def test_evolving_skies_draft_audit_documents_assumption_backed_rows_and_named_card_exclusions():
    audit = SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT_AUDIT

    assert audit["probability_model_status"] == "best_available_empirical_draft"
    assert audit["runtime_remains_disabled"] is True
    assert audit["source_rows_used_with_assumptions"]
    assert audit["parent_rows_used_with_assumptions"]
    assert "Umbreon VMAX alternate-art 0.05% (~1/2000)" in audit["named_card_rows_excluded"]
    assert (
        audit["named_card_rows_excluded"]["Umbreon VMAX alternate-art 0.05% (~1/2000)"]
        == "named_card_observation_rows_only"
    )


def test_bucket_classification_audit_status_is_complete():
    audit = SetEvolvingSkiesConfig.EVOLVING_SKIES_BUCKET_CLASSIFICATION_AUDIT
    assert audit["status"] == "complete"
    assert audit["mapped_variants"] == 144
    assert audit["unmapped_variants"] == 0
    assert audit["overlapping_variants"] == 0


# ---------------------------------------------------------------------------
# Name-disambiguation resolver tests (tiny fake DataFrames)
# ---------------------------------------------------------------------------

class _EvolvingSkiesMapping:
    """Proxy that exposes only the SLOT_SCHEMA_OUTCOME_POOL_MAPPING."""
    SLOT_SCHEMA_OUTCOME_POOL_MAPPING = SetEvolvingSkiesConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING


def _resolve_umbreon(name: str, rarity: str, card_number: str) -> List[str]:
    """Apply the full EVS mapping to a single-row DataFrame and return the buckets it lands in."""
    df = pd.DataFrame([{
        "name": name,
        "rarity": rarity,
        "printing_type": "holo",
        "card_number": card_number,
    }])
    pools = apply_slot_schema_outcome_pool_mapping(
        _EvolvingSkiesMapping, df, allow_empty_pools=True
    )
    return [bucket for bucket, pool_df in pools.items() if not pool_df.empty]


def test_umbreon_v_resolves_to_regular_v():
    buckets = _resolve_umbreon("Umbreon V", "Ultra Rare", "94")
    assert buckets == ["regular v"], f"Expected ['regular v'], got {buckets}"


def test_umbreon_v_full_art_resolves_to_full_art_v():
    buckets = _resolve_umbreon("Umbreon V (Full Art)", "Ultra Rare", "179")
    assert buckets == ["full art v"], f"Expected ['full art v'], got {buckets}"


def test_umbreon_v_alternate_full_art_resolves_to_alternate_art_v():
    buckets = _resolve_umbreon("Umbreon V (Alternate Full Art)", "Ultra Rare", "188")
    assert buckets == ["alternate art v"], f"Expected ['alternate art v'], got {buckets}"


def test_umbreon_vmax_ultra_rare_resolves_to_regular_vmax():
    buckets = _resolve_umbreon("Umbreon VMAX", "Ultra Rare", "95")
    assert buckets == ["regular vmax"], f"Expected ['regular vmax'], got {buckets}"


def test_umbreon_vmax_secret_rare_resolves_to_rainbow_vmax():
    """Umbreon VMAX (#214, Secret Rare) is a rainbow VMAX — distinguished by rarity + number."""
    buckets = _resolve_umbreon("Umbreon VMAX", "Secret Rare", "214")
    assert buckets == ["rainbow vmax"], f"Expected ['rainbow vmax'], got {buckets}"


def test_umbreon_vmax_alternate_art_secret_resolves_to_alternate_art_vmax():
    buckets = _resolve_umbreon("Umbreon VMAX Alternate Art Secret", "Secret Rare", "215")
    assert buckets == ["alternate art vmax"], f"Expected ['alternate art vmax'], got {buckets}"


def test_gold_card_resolves_to_gold_secret_rare():
    """A Secret Rare card numbered 226–237 (e.g. Raihan #234) resolves to gold secret rare."""
    df = _gold_card_row()
    pools = apply_slot_schema_outcome_pool_mapping(
        _EvolvingSkiesMapping, df, allow_empty_pools=True
    )
    matched = [b for b, p in pools.items() if not p.empty]
    assert matched == ["gold secret rare"], f"Expected ['gold secret rare'], got {matched}"


def test_reverse_holo_rare_does_not_enter_rare_slot_rare_bucket():
    """A reverse-holo Rare variant must be excluded from the rare bucket."""
    df = _reverse_holo_rare_row()
    pools = apply_slot_schema_outcome_pool_mapping(
        _EvolvingSkiesMapping, df, allow_empty_pools=True
    )
    # The row must not appear in ANY bucket.
    for bucket, pool_df in pools.items():
        assert pool_df.empty, (
            f"Reverse-holo Rare variant incorrectly entered bucket {bucket!r}"
        )


def test_umbreon_family_has_no_overlapping_bucket_assignments():
    """Each Umbreon variant must land in exactly one bucket and no two share a bucket."""
    df = _umbreon_family_df()
    pools = apply_slot_schema_outcome_pool_mapping(
        _EvolvingSkiesMapping, df, allow_empty_pools=True
    )
    bucket_assignments: Dict[str, List[str]] = {}  # card_number -> [buckets]
    for bucket, pool_df in pools.items():
        if pool_df.empty:
            continue
        for _, row in pool_df.iterrows():
            key = f"{row['name']}#{row['card_number']}"
            bucket_assignments.setdefault(key, []).append(bucket)

    for variant, buckets in bucket_assignments.items():
        assert len(buckets) == 1, (
            f"Variant {variant!r} assigned to multiple buckets: {buckets}"
        )


def test_all_umbreon_family_variants_are_mapped():
    """All six Umbreon family variants must each be assigned to exactly one bucket."""
    df = _umbreon_family_df()
    pools = apply_slot_schema_outcome_pool_mapping(
        _EvolvingSkiesMapping, df, allow_empty_pools=True
    )
    all_mapped_rows: set[str] = set()
    for pool_df in pools.values():
        if pool_df.empty:
            continue
        for _, row in pool_df.iterrows():
            key = f"{row['name']}#{row['card_number']}"
            all_mapped_rows.add(key)

    expected_variants = {
        "Umbreon V#94",
        "Umbreon V (Full Art)#179",
        "Umbreon V (Alternate Full Art)#188",
        "Umbreon VMAX#95",
        "Umbreon VMAX#214",
        "Umbreon VMAX Alternate Art Secret#215",
    }
    assert all_mapped_rows == expected_variants, (
        f"Unmapped variants: {expected_variants - all_mapped_rows}\n"
        f"Extra mapped: {all_mapped_rows - expected_variants}"
    )
