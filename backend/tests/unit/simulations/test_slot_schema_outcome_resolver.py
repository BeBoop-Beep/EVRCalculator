import pandas as pd
import pytest

from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.simulations.slotSchemaOutcomeResolver import (
    apply_slot_schema_outcome_pool_mapping,
    resolve_slot_schema_outcome_pools,
    validate_slot_schema_outcome_pool_mapping,
)


class _ResolverConfig:
    SLOT_SCHEMA_OUTCOME_POOL_MAPPING = {
        "rare": {
            "source": "rarity + printing_type",
            "card_filter": {"rarity": "Rare"},
            "variant_filter": {"printing_type": "non-holo"},
            "include_reverse_variants": False,
        }
    }


def _make_base_df():
    return pd.DataFrame(
        [
            {"name": "Rare A", "rarity": "Rare", "printing_type": "non-holo", "card_number": "1", "Price ($)": 1.0},
            {"name": "Rare Reverse", "rarity": "Rare", "printing_type": "reverse-holo", "card_number": "2", "Price ($)": 1.1},
            {"name": "Holo A", "rarity": "Holo Rare", "printing_type": "holo", "card_number": "3", "Price ($)": 2.0},
            {"name": "Blaziken V", "rarity": "Ultra Rare", "printing_type": "holo", "card_number": "120", "Price ($)": 5.0},
            {"name": "Blaziken VMAX", "rarity": "Ultra Rare", "printing_type": "holo", "card_number": "140", "Price ($)": 7.0},
            {
                "name": "Blaziken V (Full Art)",
                "rarity": "Ultra Rare",
                "printing_type": "holo",
                "card_number": "170",
                "Price ($)": 12.0,
            },
            {
                "name": "Blaziken V (Alternate Full Art)",
                "rarity": "Ultra Rare",
                "printing_type": "holo",
                "card_number": "173",
                "Price ($)": 20.0,
            },
            {"name": "Flannery", "rarity": "Ultra Rare", "printing_type": "holo", "card_number": "190", "Price ($)": 9.0},
            {
                "name": "Blaziken VMAX Alternate Art Secret",
                "rarity": "Secret Rare",
                "printing_type": "holo",
                "card_number": "201",
                "Price ($)": 60.0,
            },
            {"name": "Ice Rider Calyrex VMAX", "rarity": "Secret Rare", "printing_type": "holo", "card_number": "205", "Price ($)": 25.0},
            {"name": "Flannery Rainbow", "rarity": "Secret Rare", "printing_type": "holo", "card_number": "215", "Price ($)": 16.0},
            {"name": "Snorlax", "rarity": "Secret Rare", "printing_type": "holo", "card_number": "225", "Price ($)": 18.0},
            {"name": "Secret Reverse", "rarity": "Secret Rare", "printing_type": "reverse-holo", "card_number": "226", "Price ($)": 10.0},
        ]
    )


def test_exact_rarity_and_printing_type_filters_work():
    result = apply_slot_schema_outcome_pool_mapping(_ResolverConfig, _make_base_df())
    assert list(result.keys()) == ["rare"]
    assert result["rare"]["name"].tolist() == ["Rare A"]


def test_card_number_range_filter_works():
    class _Config:
        SLOT_SCHEMA_OUTCOME_POOL_MAPPING = {
            "full art trainer": {
                "card_filter": {"rarity": "Ultra Rare", "card_number_range": "186-198"},
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
            }
        }

    result = apply_slot_schema_outcome_pool_mapping(_Config, _make_base_df())
    assert result["full art trainer"]["name"].tolist() == ["Flannery"]


def test_name_contains_name_not_contains_name_contains_all_and_endswith_pattern_work():
    class _Config:
        SLOT_SCHEMA_OUTCOME_POOL_MAPPING = {
            "regular v": {
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "card_number_max": 159,
                    "name_pattern": "endswith(' V')",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
            },
            "full art v": {
                "card_filter": {
                    "rarity": "Ultra Rare",
                    "name_contains": "(Full Art)",
                    "name_not_contains": "Alternate",
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
            },
            "alternate art vmax": {
                "card_filter": {
                    "rarity": "Secret Rare",
                    "name_contains": "Alternate Art Secret",
                    "name_contains_all": ["VMAX"],
                },
                "variant_filter": {"printing_type": "holo"},
                "include_reverse_variants": False,
            },
        }

    result = apply_slot_schema_outcome_pool_mapping(_Config, _make_base_df())
    assert result["regular v"]["name"].tolist() == ["Blaziken V"]
    assert result["full art v"]["name"].tolist() == ["Blaziken V (Full Art)"]
    assert result["alternate art vmax"]["name"].tolist() == ["Blaziken VMAX Alternate Art Secret"]


def test_reverse_holo_rows_excluded_from_rare_slot_outcomes_when_configured():
    class _Config:
        SLOT_SCHEMA_OUTCOME_POOL_MAPPING = {
            "gold secret rare": {
                "card_filter": {"rarity": "Secret Rare", "card_number_range": "222-233"},
                "variant_filter": {},
                "include_reverse_variants": False,
            }
        }

    result = apply_slot_schema_outcome_pool_mapping(_Config, _make_base_df())
    assert result["gold secret rare"]["name"].tolist() == ["Snorlax"]


def test_missing_required_columns_fail_loudly():
    df = pd.DataFrame([{"name": "X", "rarity": "Rare", "card_number": "1"}])
    with pytest.raises(ValueError, match="unknown filter key 'printing_type'"):
        apply_slot_schema_outcome_pool_mapping(_ResolverConfig, df)


def test_unknown_filter_operators_fail_loudly():
    class _BadConfig:
        SLOT_SCHEMA_OUTCOME_POOL_MAPPING = {
            "rare": {
                "card_filter": {"rarity": "Rare", "name_starts_with": "A"},
                "variant_filter": {"printing_type": "non-holo"},
            }
        }

    with pytest.raises(ValueError, match="unknown filter key 'name_starts_with'"):
        validate_slot_schema_outcome_pool_mapping(_BadConfig, available_columns=_make_base_df().columns)


def test_empty_mapped_pools_fail_loudly_unless_explicitly_allowed():
    class _EmptyConfig:
        SLOT_SCHEMA_OUTCOME_POOL_MAPPING = {
            "rare": {
                "card_filter": {"rarity": "Not A Real Rarity"},
                "variant_filter": {"printing_type": "non-holo"},
            }
        }

    with pytest.raises(ValueError, match="resolved to an empty pool"):
        apply_slot_schema_outcome_pool_mapping(_EmptyConfig, _make_base_df())

    result = apply_slot_schema_outcome_pool_mapping(_EmptyConfig, _make_base_df(), allow_empty_pools=True)
    assert result["rare"].empty


def test_resolve_slot_schema_outcome_pools_accepts_dataframe_and_mapping_inputs():
    df = _make_base_df()
    from_df = resolve_slot_schema_outcome_pools(_ResolverConfig, df)
    from_mapping = resolve_slot_schema_outcome_pools(_ResolverConfig, {"rare": df.iloc[:3].copy(), "rest": df.iloc[3:].copy()})
    assert from_df["rare"]["name"].tolist() == ["Rare A"]
    assert from_mapping["rare"]["name"].tolist() == ["Rare A"]


def test_chilling_reign_runtime_intended_mapping_keys_match_audit_outcomes_and_runtime_stays_blocked():
    audit_outcomes = set(SetChillingReignConfig.CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT["outcomes"].keys())
    runtime_mapping_outcomes = set(SetChillingReignConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())

    assert runtime_mapping_outcomes == audit_outcomes
    assert {"rare", "holo rare", "regular v", "regular vmax"}.issubset(runtime_mapping_outcomes)
    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY")
    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert SetChillingReignConfig.RARE_SLOT_PROBABILITY == SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT
    assert (
        SetChillingReignConfig.SLOT_SCHEMA_SOURCE_CONFIDENCE["status"]
        == "runtime_candidate_best_available_empirical"
    )


def test_chilling_reign_mapping_resolves_all_intended_outcomes_with_tiny_dataframe():
    result = apply_slot_schema_outcome_pool_mapping(SetChillingReignConfig, _make_base_df())

    expected_name_by_outcome = {
        "rare": "Rare A",
        "holo rare": "Holo A",
        "regular v": "Blaziken V",
        "regular vmax": "Blaziken VMAX",
        "full art v": "Blaziken V (Full Art)",
        "full art trainer": "Flannery",
        "alternate art v": "Blaziken V (Alternate Full Art)",
        "alternate art vmax": "Blaziken VMAX Alternate Art Secret",
        "rainbow trainer": "Flannery Rainbow",
        "rainbow vmax": "Ice Rider Calyrex VMAX",
        "gold secret rare": "Snorlax",
    }

    assert set(result.keys()) == set(expected_name_by_outcome.keys())
    for outcome, expected_name in expected_name_by_outcome.items():
        assert result[outcome]["name"].tolist() == [expected_name]
