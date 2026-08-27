from backend.desirability.collector_appeal_inputs import select_subject_paths
from backend.domain.pokemon.rip_decision_metrics import exact_card_probability_contract


def test_subject_paths_publish_the_same_cumulative_probability_counts_as_top_chase():
    probability = 1 / 1533
    paths = select_subject_paths({"cards": [{
        "canonical_card_id": "chase-1",
        "card_name": "Chase",
        "rarity": "Special Illustration Rare",
        "pull_probability": probability,
    }]})

    elite = paths["elitePath"]
    canonical = exact_card_probability_contract(probability)
    assert canonical["packsFor50PercentChance"] == 1063
    assert canonical["packsFor90PercentChance"] == 3529
    assert elite["packsFor50PercentChance"] == canonical["packsFor50PercentChance"]
    assert elite["packsFor90PercentChance"] == canonical["packsFor90PercentChance"]


def test_elite_and_accessible_paths_use_their_own_probability_without_snapshot_join():
    paths = select_subject_paths({"cards": [
        {"canonical_card_id": "same-name-elite", "card_name": "Example ex", "pull_probability": 1 / 1500, "rarity_priority": 10},
        {"canonical_card_id": "same-name-accessible", "card_name": "Example ex", "pull_probability": 1 / 100, "rarity_priority": 2},
    ]})
    elite = paths["elitePath"]
    accessible = paths["accessiblePath"]
    assert elite["canonicalCardId"] == "same-name-elite"
    assert accessible["canonicalCardId"] == "same-name-accessible"
    elite_contract = exact_card_probability_contract(1 / 1500)
    accessible_contract = exact_card_probability_contract(1 / 100)
    assert elite["packsFor50PercentChance"] == elite_contract["packsFor50PercentChance"]
    assert elite["packsFor90PercentChance"] == elite_contract["packsFor90PercentChance"]
    assert accessible["packsFor50PercentChance"] == accessible_contract["packsFor50PercentChance"]
    assert accessible["packsFor90PercentChance"] == accessible_contract["packsFor90PercentChance"]
    assert elite["packsFor50PercentChance"] != accessible["packsFor50PercentChance"]
    assert elite["packsFor90PercentChance"] != accessible["packsFor90PercentChance"]


def test_collector_path_card_outside_top_25_chase_cap_still_gets_thresholds():
    probability = 1 / 777
    paths = select_subject_paths({"cards": [{
        "canonical_card_id": "collector-only-rank-26",
        "card_name": "Collector-only printing",
        "pull_probability": probability,
        # Deliberately no Top Chase snapshot/rank input: Collector paths are
        # serialized directly from the subject index, outside that storage cap.
    }]})

    canonical = exact_card_probability_contract(probability)
    assert paths["elitePath"]["canonicalCardId"] == "collector-only-rank-26"
    assert paths["elitePath"]["packsFor50PercentChance"] == canonical["packsFor50PercentChance"]
    assert paths["elitePath"]["packsFor90PercentChance"] == canonical["packsFor90PercentChance"]


def test_collector_paths_import_the_canonical_contract_not_threshold_math():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[3] / "desirability" / "collector_appeal_inputs.py").read_text(encoding="utf-8")
    assert "exact_card_probability_contract" in source
    assert "packs_for_cumulative_probability" not in source
    assert "math.log" not in source
