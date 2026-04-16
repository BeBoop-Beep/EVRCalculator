import pytest

from backend.simulations.utils.packStateModels.mergePackStateModels import merge_pack_state_models


BASE_MODEL = {
    "state_probabilities": {
        "baseline": 0.70,
        "double_rare_only": 0.20,
        "sir_only": 0.10,
    },
    "state_outcomes": {
        "baseline": {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"},
        "double_rare_only": {
            "rare": "double rare",
            "reverse_1": "regular reverse",
            "reverse_2": "regular reverse",
        },
        "sir_only": {
            "rare": "rare",
            "reverse_1": "regular reverse",
            "reverse_2": "special illustration rare",
        },
    },
    "constraints": {
        "primary_hits": {"double rare", "ultra rare", "illustration rare"},
        "exclusive_hits": {"special illustration rare", "hyper rare"},
        "bonus_hits": {"ace spec rare", "poke ball pattern"},
        "max_major_hits": 2,
        "max_non_regular_hits": 2,
        "max_exclusive_hits": 1,
    },
}


def test_merge_pack_state_models_overrides_and_adds_states():
    overrides = {
        "state_probabilities": {
            "baseline": 0.55,
            "black_white_rare_only": 0.05,
        },
        "state_outcomes": {
            "black_white_rare_only": {
                "rare": "black white rare",
                "reverse_1": "regular reverse",
                "reverse_2": "regular reverse",
            }
        },
    }

    merged = merge_pack_state_models(BASE_MODEL, overrides)
    assert "black_white_rare_only" in merged["state_outcomes"]
    assert pytest.approx(1.0, abs=1e-8) == sum(merged["state_probabilities"].values())


def test_merge_pack_state_models_merges_constraints_with_set_union_for_hit_categories():
    overrides = {
        "constraints": {
            "exclusive_hits": {"mega hyper rare"},
            "bonus_hits": {"master ball pattern"},
            "max_major_hits": 3,
        }
    }

    merged = merge_pack_state_models(BASE_MODEL, overrides)
    assert "mega hyper rare" in merged["constraints"]["exclusive_hits"]
    assert "master ball pattern" in merged["constraints"]["bonus_hits"]
    assert merged["constraints"]["max_major_hits"] == 3


def test_merge_pack_state_models_rejects_incomplete_state_slots():
    overrides = {
        "state_outcomes": {
            "bad_state": {
                "rare": "rare",
                "reverse_1": "regular reverse",
            }
        }
    }

    with pytest.raises(ValueError, match="must define exactly"):
        merge_pack_state_models(BASE_MODEL, overrides)


def test_merge_pack_state_models_requires_outcomes_for_all_probability_states():
    overrides = {
        "state_probabilities": {
            "new_state_without_outcome": 0.2,
        }
    }

    with pytest.raises(ValueError, match="Missing slot outcomes"):
        merge_pack_state_models(BASE_MODEL, overrides)
