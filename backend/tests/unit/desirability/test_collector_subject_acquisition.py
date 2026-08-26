from backend.desirability.collector_appeal_inputs import select_subject_paths
from backend.domain.pokemon.rip_decision_metrics import exact_card_probability_contract


def test_subject_paths_publish_the_same_cumulative_probability_counts_as_top_chase():
    probability = 1 / 480
    paths = select_subject_paths({"cards": [{
        "canonical_card_id": "chase-1",
        "card_name": "Chase",
        "rarity": "Special Illustration Rare",
        "pull_probability": probability,
    }]})

    elite = paths["elitePath"]
    canonical = exact_card_probability_contract(probability)
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
    assert elite["packsFor50PercentChance"] == exact_card_probability_contract(1 / 1500)["packsFor50PercentChance"]
    assert accessible["packsFor50PercentChance"] == exact_card_probability_contract(1 / 100)["packsFor50PercentChance"]
    assert elite["packsFor90PercentChance"] != accessible["packsFor90PercentChance"]


def test_collector_paths_import_the_canonical_contract_not_threshold_math():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[3] / "desirability" / "collector_appeal_inputs.py").read_text(encoding="utf-8")
    assert "exact_card_probability_contract" in source
    assert "packs_for_cumulative_probability" not in source
    assert "math.log" not in source
