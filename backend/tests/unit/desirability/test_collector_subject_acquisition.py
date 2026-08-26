from backend.desirability.collector_appeal_inputs import select_subject_paths
from backend.domain.pokemon.rip_decision_metrics import packs_for_cumulative_probability


def test_subject_paths_publish_the_same_cumulative_probability_counts_as_top_chase():
    probability = 1 / 480
    paths = select_subject_paths({"cards": [{
        "canonical_card_id": "chase-1",
        "card_name": "Chase",
        "rarity": "Special Illustration Rare",
        "pull_probability": probability,
    }]})

    elite = paths["elitePath"]
    assert elite["packsFor50PercentChance"] == packs_for_cumulative_probability(probability, 0.50)
    assert elite["packsFor90PercentChance"] == packs_for_cumulative_probability(probability, 0.90)
