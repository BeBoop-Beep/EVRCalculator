import random

import pytest

from backend.simulations.slotSchemaSimulator import (
    simulate_slot_schema_pack,
    simulate_slot_schema_packs,
)


class _StandardPreSVDummyConfig:
    PACK_STRUCTURE = {
        "common_slots": 5,
        "uncommon_slots": 3,
        "rare_family_slots": [
            {
                "name": "reverse_slot",
                "role": "reverse_parallel",
                "probability_attr": "REVERSE_SLOT_PROBABILITIES",
                "probability_key": "slot_1",
                "default_outcome": "regular reverse",
            },
            {
                "name": "rare_slot",
                "role": "rare_or_better",
                "probability_attr": "RARE_SLOT_PROBABILITY",
                "default_outcome": "rare",
            },
        ],
    }
    REVERSE_SLOT_PROBABILITIES = {"slot_1": {"regular reverse": 1.0}}
    RARE_SLOT_PROBABILITY = {"rare": 1.0}


class _TwoReverseSlotsDummyConfig:
    PACK_STRUCTURE = {
        "common_slots": 4,
        "uncommon_slots": 3,
        "rare_family_slots": [
            {
                "name": "reverse_1",
                "role": "reverse_parallel",
                "default_outcome": "regular reverse",
            },
            {
                "name": "reverse_2",
                "role": "reverse_parallel",
                "default_outcome": "regular reverse",
            },
            {
                "name": "rare",
                "role": "rare_or_better",
                "default_outcome": "rare",
            },
        ],
    }


class _FourCardSpecialPackConfig:
    PACK_STRUCTURE = {
        "common_slots": 0,
        "uncommon_slots": 0,
        "rare_family_slots": [
            {"name": "slot_1", "role": "special_main", "default_outcome": "holo rare"},
            {"name": "slot_2", "role": "special_main", "default_outcome": "holo rare"},
            {"name": "slot_3", "role": "special_subset_or_main", "default_outcome": "holo rare"},
            {"name": "slot_4", "role": "special_subset_or_main", "default_outcome": "holo rare"},
        ],
    }


class _HoloGuaranteedDummyConfig:
    PACK_STRUCTURE = {
        "common_slots": 5,
        "uncommon_slots": 3,
        "rare_family_slots": [
            {"name": "reverse_slot", "role": "reverse_parallel", "default_outcome": "regular reverse"},
            {
                "name": "holo_slot",
                "role": "guaranteed_holo_or_better",
                "probability_attr": "HOLO_GUARANTEED_SLOT_TABLE",
            },
        ],
    }
    HOLO_GUARANTEED_SLOT_TABLE = {"holo rare": 1.0}


class _ReverseAndRareHitCooccurConfig:
    PACK_STRUCTURE = {
        "common_slots": 5,
        "uncommon_slots": 3,
        "rare_family_slots": [
            {
                "name": "reverse_hit_slot",
                "role": "reverse_subset",
                "probability_attr": "REVERSE_SLOT_PROBABILITIES",
                "probability_key": "slot_1",
            },
            {
                "name": "rare_hit_slot",
                "role": "rare_or_better",
                "probability_attr": "RARE_SLOT_PROBABILITY",
            },
        ],
    }
    REVERSE_SLOT_PROBABILITIES = {"slot_1": {"illustration rare": 1.0}}
    RARE_SLOT_PROBABILITY = {"ultra rare": 1.0}


class _MissingProbabilityAttrConfig:
    PACK_STRUCTURE = {
        "common_slots": 0,
        "uncommon_slots": 0,
        "rare_family_slots": [
            {
                "name": "slot_1",
                "role": "rare_or_better",
                "probability_attr": "DOES_NOT_EXIST",
            }
        ],
    }


class _BadProbabilityKeyConfig:
    PACK_STRUCTURE = {
        "common_slots": 0,
        "uncommon_slots": 0,
        "rare_family_slots": [
            {
                "name": "slot_1",
                "role": "reverse_parallel",
                "probability_attr": "REVERSE_SLOT_PROBABILITIES",
                "probability_key": "unknown_slot",
            }
        ],
    }
    REVERSE_SLOT_PROBABILITIES = {"slot_1": {"regular reverse": 1.0}}


def _build_fake_pool():
    return {
        "common": [
            {"id": "c1", "name": "Common 1", "category": "common", "value": 0.1},
            {"id": "c2", "name": "Common 2", "category": "common", "value": 0.2},
        ],
        "uncommon": [
            {"id": "u1", "name": "Uncommon 1", "category": "uncommon", "value": 0.3},
            {"id": "u2", "name": "Uncommon 2", "category": "uncommon", "value": 0.4},
        ],
        "regular reverse": [
            {"id": "rvr1", "name": "Reverse 1", "category": "regular reverse", "value": 0.5},
        ],
        "reverse": [
            {"id": "rv1", "name": "Reverse Alias", "category": "regular reverse", "value": 0.55},
        ],
        "rare": [
            {"id": "r1", "name": "Rare 1", "category": "rare", "value": 1.0},
        ],
        "holo rare": [
            {"id": "h1", "name": "Holo Rare 1", "category": "holo rare", "value": 1.5},
        ],
        "illustration rare": [
            {
                "id": "ir1",
                "name": "Illustration Rare 1",
                "category": "illustration rare",
                "value": 5.0,
            }
        ],
        "ultra rare": [
            {"id": "ur1", "name": "Ultra Rare 1", "category": "ultra rare", "value": 7.0},
        ],
    }


def test_standard_pre_sv_5311_pack_returns_exactly_10_cards():
    pack = simulate_slot_schema_pack(
        _StandardPreSVDummyConfig(),
        _build_fake_pool(),
        rng=random.Random(7),
    )
    assert pack["total_cards"] == 10


def test_standard_pre_sv_pack_has_expected_slot_breakdown():
    pack = simulate_slot_schema_pack(
        _StandardPreSVDummyConfig(),
        _build_fake_pool(),
        rng=random.Random(11),
    )

    cards = pack["cards"]
    assert sum(1 for c in cards if c["slot_group"] == "common") == 5
    assert sum(1 for c in cards if c["slot_group"] == "uncommon") == 3
    assert sum(1 for c in cards if c["outcome"] == "regular reverse") == 1
    assert sum(1 for c in cards if c["outcome"] == "rare") == 1


def test_two_reverse_slots_can_be_represented_and_return_10_cards():
    pack = simulate_slot_schema_pack(
        _TwoReverseSlotsDummyConfig(),
        _build_fake_pool(),
        rng=random.Random(13),
    )

    assert pack["total_cards"] == 10
    assert sum(1 for c in pack["cards"] if c["slot_role"] == "reverse_parallel") == 2


def test_four_card_special_pack_returns_exactly_4_cards():
    pack = simulate_slot_schema_pack(
        _FourCardSpecialPackConfig(),
        _build_fake_pool(),
        rng=random.Random(17),
    )

    assert pack["total_cards"] == 4
    assert all(c["slot_group"] == "rare_family" for c in pack["cards"])


def test_holo_guaranteed_slot_works_without_regular_rare_outcome():
    pack = simulate_slot_schema_pack(
        _HoloGuaranteedDummyConfig(),
        _build_fake_pool(),
        rng=random.Random(19),
    )

    outcomes = [c["outcome"] for c in pack["cards"] if c["slot_group"] == "rare_family"]
    assert "holo rare" in outcomes


def test_reverse_hit_and_rare_hit_can_cooccur():
    pack = simulate_slot_schema_pack(
        _ReverseAndRareHitCooccurConfig(),
        _build_fake_pool(),
        rng=random.Random(23),
    )

    outcomes = [c["outcome"] for c in pack["cards"] if c["slot_group"] == "rare_family"]
    assert "illustration rare" in outcomes
    assert "ultra rare" in outcomes


def test_missing_pool_for_required_outcome_fails_loudly():
    pool = _build_fake_pool()
    del pool["rare"]

    with pytest.raises(ValueError, match="Missing card pool for outcome='rare'"):
        simulate_slot_schema_pack(_StandardPreSVDummyConfig(), pool, rng=random.Random(29))


def test_missing_probability_table_referenced_by_probability_attr_fails_loudly():
    with pytest.raises(ValueError, match="references probability_attr='DOES_NOT_EXIST'"):
        simulate_slot_schema_pack(_MissingProbabilityAttrConfig(), _build_fake_pool(), rng=random.Random(31))


def test_bad_probability_key_fails_loudly():
    with pytest.raises(ValueError, match="references probability_key='unknown_slot'"):
        simulate_slot_schema_pack(_BadProbabilityKeyConfig(), _build_fake_pool(), rng=random.Random(37))


def test_simulate_multiple_packs_returns_basic_aggregate_shape():
    results = simulate_slot_schema_packs(
        _StandardPreSVDummyConfig(),
        _build_fake_pool(),
        num_packs=5,
        rng=random.Random(41),
    )

    assert len(results["packs"]) == 5
    assert len(results["values"]) == 5
    assert "mean" in results
    assert "rarity_pull_counts" in results
    assert "rarity_value_totals" in results
