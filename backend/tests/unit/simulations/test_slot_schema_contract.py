import pytest

from backend.simulations.slotSchemaContract import (
    compute_total_modeled_slots,
    get_pack_structure,
    validate_pack_structure,
    validate_slot_schema_config,
)


class _StandardPreSVConfig:
    PACK_STRUCTURE = {
        "common_slots": 5,
        "uncommon_slots": 3,
        "rare_family_slots": [
            {
                "name": "rare_slot_1",
                "role": "reverse_parallel",
                "probability_attr": "REVERSE_SLOT_PROBABILITIES",
                "probability_key": "slot_1",
                "default_outcome": "regular reverse",
            },
            {
                "name": "rare_slot_2",
                "role": "rare_or_better",
                "probability_attr": "RARE_SLOT_PROBABILITY",
                "default_outcome": "rare",
            },
        ],
    }


def test_standard_pre_sv_5311_shape_passes_validation():
    summary = validate_slot_schema_config(_StandardPreSVConfig())
    assert summary["common_slots"] == 5
    assert summary["uncommon_slots"] == 3
    assert summary["rare_family_slot_count"] == 2
    assert summary["total_modeled_slots"] == 10


def test_sv_mega_like_4321_shape_can_be_represented():
    pack_structure = {
        "common_slots": 4,
        "uncommon_slots": 3,
        "rare_family_slots": [
            {
                "name": "reverse_1",
                "role": "reverse_parallel",
                "probability_attr": "REVERSE_SLOT_PROBABILITIES",
                "probability_key": "slot_1",
            },
            {
                "name": "reverse_2",
                "role": "reverse_parallel",
                "probability_attr": "REVERSE_SLOT_PROBABILITIES",
                "probability_key": "slot_2",
            },
            {
                "name": "rare",
                "role": "rare_or_better",
                "probability_attr": "RARE_SLOT_PROBABILITY",
            },
        ],
    }

    summary = validate_pack_structure(pack_structure)
    assert summary["total_modeled_slots"] == 10


def test_celebrations_like_zero_zero_four_structure_passes():
    pack_structure = {
        "common_slots": 0,
        "uncommon_slots": 0,
        "rare_family_slots": [
            {"name": "slot_1", "role": "rare_or_better", "default_outcome": "holo rare"},
            {"name": "slot_2", "role": "rare_or_better", "default_outcome": "holo rare"},
            {"name": "slot_3", "role": "rare_or_better", "default_outcome": "holo rare"},
            {"name": "slot_4", "role": "rare_or_better", "default_outcome": "holo rare"},
        ],
    }

    summary = validate_pack_structure(pack_structure)
    assert summary["total_modeled_slots"] == 4


def test_holo_guaranteed_slot_with_no_rare_default_is_allowed():
    pack_structure = {
        "common_slots": 5,
        "uncommon_slots": 3,
        "rare_family_slots": [
            {
                "name": "reverse_slot",
                "role": "reverse_parallel",
                "default_outcome": "regular reverse",
            },
            {
                "name": "guaranteed_holo_slot",
                "role": "guaranteed_holo_or_better",
                "default_outcome": "holo rare",
            },
        ],
    }

    summary = validate_pack_structure(pack_structure)
    assert summary["total_modeled_slots"] == 10


def test_reverse_subset_capable_role_passes():
    pack_structure = {
        "common_slots": 5,
        "uncommon_slots": 3,
        "rare_family_slots": [
            {
                "name": "reverse_slot",
                "role": "reverse_subset",
                "probability_attr": "REVERSE_SLOT_PROBABILITIES",
                "probability_key": "slot_1",
                "default_outcome": "regular reverse",
            },
            {"name": "rare_slot", "role": "rare_or_better", "default_outcome": "rare"},
        ],
    }

    validate_pack_structure(pack_structure)


def test_missing_pack_structure_fails_with_clear_error():
    class _NoPackStructure:
        pass

    with pytest.raises(ValueError, match="PACK_STRUCTURE is required for slot-schema configs"):
        get_pack_structure(_NoPackStructure())


def test_missing_rare_family_slots_fails():
    with pytest.raises(ValueError, match="missing required fields: rare_family_slots"):
        validate_pack_structure({"common_slots": 5, "uncommon_slots": 3})


def test_duplicate_rare_slot_names_fail():
    with pytest.raises(ValueError, match="duplicate slot names"):
        validate_pack_structure(
            {
                "common_slots": 5,
                "uncommon_slots": 3,
                "rare_family_slots": [
                    {"name": "slot_a", "role": "reverse_parallel"},
                    {"name": "slot_a", "role": "rare_or_better"},
                ],
            }
        )


def test_invalid_role_fails():
    with pytest.raises(ValueError, match="is not allowed"):
        validate_pack_structure(
            {
                "common_slots": 5,
                "uncommon_slots": 3,
                "rare_family_slots": [{"name": "slot_a", "role": "totally_new_role"}],
            }
        )


def test_bad_common_uncommon_counts_fail():
    with pytest.raises(ValueError, match="common_slots must be a non-negative integer"):
        validate_pack_structure(
            {
                "common_slots": -1,
                "uncommon_slots": 3,
                "rare_family_slots": [{"name": "slot_a", "role": "rare_or_better"}],
            }
        )

    with pytest.raises(ValueError, match="uncommon_slots must be a non-negative integer"):
        validate_pack_structure(
            {
                "common_slots": 5,
                "uncommon_slots": "3",
                "rare_family_slots": [{"name": "slot_a", "role": "rare_or_better"}],
            }
        )


def test_bad_probability_field_types_fail():
    with pytest.raises(ValueError, match="probability_attr must be of type str"):
        validate_pack_structure(
            {
                "common_slots": 5,
                "uncommon_slots": 3,
                "rare_family_slots": [
                    {
                        "name": "slot_a",
                        "role": "reverse_parallel",
                        "probability_attr": 123,
                    }
                ],
            }
        )

    with pytest.raises(ValueError, match="probability_key must be of type str"):
        validate_pack_structure(
            {
                "common_slots": 5,
                "uncommon_slots": 3,
                "rare_family_slots": [
                    {
                        "name": "slot_a",
                        "role": "reverse_parallel",
                        "probability_attr": "REVERSE_SLOT_PROBABILITIES",
                        "probability_key": 7,
                    }
                ],
            }
        )


def test_total_modeled_slot_count_helper_returns_expected_values():
    assert (
        compute_total_modeled_slots(_StandardPreSVConfig.PACK_STRUCTURE)
        == 5 + 3 + len(_StandardPreSVConfig.PACK_STRUCTURE["rare_family_slots"])
    )
    assert (
        compute_total_modeled_slots(
            {
                "common_slots": 0,
                "uncommon_slots": 0,
                "rare_family_slots": [{"name": "a", "role": "rare_or_better"}] * 4,
            }
        )
        == 4
    )
