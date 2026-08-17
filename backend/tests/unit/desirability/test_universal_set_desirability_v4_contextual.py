from backend.desirability.universal_set_desirability import (
    build_contextual_chase_subjects,
    compute_universal_set_desirability,
    compute_universal_set_desirability_v4,
)


def subject(ref, name, demand):
    return {
        "subject_key": f"ref:{ref}", "pokemon_reference_id": ref,
        "subject_name": name, "max_desirability_score": demand,
        "rarity_buckets_present": ["major_hit"], "card_count": 1,
    }


def card(ref, name, ev, price=10, rarity="Illustration Rare", probability=.01):
    return {
        "pokemon_reference_id": ref, "card_id": name, "card_name": name,
        "ev_contribution": ev, "market_value": price, "rarity": rarity,
        "modeled_probability": probability,
    }


def test_accessible_popular_subject_cannot_displace_actual_chases():
    rollups = [subject(25, "Pikachu", 96), subject(129, "Magikarp", 75),
               subject(26, "Raichu", 82), subject(248, "Tyranitar", 78),
               subject(959, "Tinkaton", 70), subject(6, "Charizard", 94)]
    evidence = [card(129, "Magikarp 203", 3.0), card(26, "Raichu 211", 2.0),
                card(248, "Tyranitar 222", 1.5), card(959, "Tinkaton 262", 1.2),
                card(6, "Charizard ex", 1.0), card(25, "Pikachu ex", .001, 4, "Double Rare", .10)]
    result = compute_universal_set_desirability_v4(rollups, evidence)
    assert [row["pokemon_reference_id"] for row in result["top_subjects"]] == [6, 26, 248]
    pikachu = next(row for row in result["modeled_subjects"] if row["pokemon_reference_id"] == 25)
    assert pikachu["role"] == "supporting_roster"
    assert pikachu["max_desirability_score"] == 96


def test_same_pokemon_gets_set_specific_role_without_changing_demand():
    rollups = [subject(25, "Pikachu", 86.64), subject(129, "Magikarp", 70)]
    flagship = build_contextual_chase_subjects(
        rollups, [card(25, "Pikachu ex SIR", 3), card(129, "Magikarp", .001)])
    # Use enough subjects for the low-share Pikachu representation to remain supporting.
    many = [subject(i, f"P{i}", 60 + i) for i in range(1, 7)] + [subject(25, "Pikachu", 86.64)]
    cards = [card(i, f"Chase {i}", 10 - i) for i in range(1, 7)] + [card(25, "Pikachu ex", .0001)]
    low = build_contextual_chase_subjects(many, cards)
    assert next(x for x in low["all_subjects"] if x["pokemon_reference_id"] == 25)["role"] == "supporting_roster"
    assert next(x for x in flagship["all_subjects"] if x["pokemon_reference_id"] == 25)["role"] == "meaningful_chase"
    assert next(x for x in low["all_subjects"] if x["pokemon_reference_id"] == 25)["max_desirability_score"] == 86.64


def test_duplicate_cards_collapse_to_one_subject_and_trainers_are_ignored():
    rollups = [subject(25, "Pikachu", 90)]
    evidence = [card(25, "Pikachu A", 2), card(25, "Pikachu B", 1),
                {"card_name": "Iono", "ev_contribution": 50}]
    context = build_contextual_chase_subjects(rollups, evidence)
    assert len(context["all_subjects"]) == 1
    assert context["all_subjects"][0]["subject_ev_contribution"] == 3
    assert context["all_subjects"][0]["representative_chase_card"]["card_name"] == "Pikachu A"


def test_missing_chase_distribution_is_explicitly_unavailable_and_v3_reproducible():
    rollups = [subject(25, "Pikachu", 90)]
    before = compute_universal_set_desirability(rollups)
    result = compute_universal_set_desirability_v4(rollups, [])
    after = compute_universal_set_desirability(rollups)
    assert result["score"] is None
    assert result["reason"] == "missing_canonical_chase_evidence"
    assert before == after


def test_subject_level_share_aggregates_multiple_subthreshold_cards():
    rollups = [subject(94, "Gengar", 84), subject(1, "Bulbasaur", 70)]
    evidence = [card(94, f"Gengar {i}", .007) for i in range(3)]
    evidence += [card(1, "Bulbasaur", .979)]
    context = build_contextual_chase_subjects(rollups, evidence, min_subject_share=.01)
    gengar = next(x for x in context["all_subjects"] if x["pokemon_reference_id"] == 94)
    assert gengar["subject_ev_share"] == .021
    assert gengar["role"] == "meaningful_chase"
    assert gengar["eligible_card_count"] == 3


def test_desirability_not_ev_assigns_strength_slot_order():
    rollups = [subject(1, "High EV", 82), subject(2, "High Demand", 88)]
    evidence = [card(1, "High EV card", .8), card(2, "High Demand card", .2)]
    result = compute_universal_set_desirability_v4(rollups, evidence)
    assert [x["pokemon_reference_id"] for x in result["top_subjects"]] == [2, 1]
    assert result["top_subjects"][0]["slot_weight"] > result["top_subjects"][1]["slot_weight"]


def test_no_unconditional_top_five_and_trainer_cannot_consume_subject_slot():
    rollups = [subject(i, f"P{i}", 60 + i) for i in range(1, 7)]
    evidence = [{"card_name": "Trainer", "ev_contribution": 95,
                 "mapping_status": "intentional_non_pokemon"}]
    evidence += [card(i, f"P{i}", .5) for i in range(1, 7)]
    result = compute_universal_set_desirability_v4(rollups, evidence)
    assert result["score"] is None
    assert result["reason"] == "no_meaningful_chase_subjects"
    assert result["chase_evidence"]["intentional_non_pokemon_card_count"] == 1


def test_representative_card_is_highest_ev_card_for_aggregated_subject():
    rollups = [subject(25, "Pikachu", 90)]
    context = build_contextual_chase_subjects(
        rollups, [card(25, "Small", .02), card(25, "Flagship", .08), card(25, "Medium", .04)]
    )
    pikachu = context["all_subjects"][0]
    assert pikachu["representative_chase_card"]["card_name"] == "Flagship"
    assert pikachu["eligible_card_count"] == 3


def test_mapping_reliability_gate_blocks_normal_score_but_not_non_pokemon_ev():
    rollups = [subject(25, "Pikachu", 90)]
    evidence = [card(25, "Pikachu", .4),
                {"card_name": "Broken", "ev_contribution": .4, "mapping_status": "unresolved"},
                {"card_name": "Trainer", "ev_contribution": .2, "mapping_status": "intentional_non_pokemon"}]
    blocked = compute_universal_set_desirability_v4(rollups, evidence, max_unresolved_ev_share=.10)
    assert blocked["score"] is None
    assert blocked["reason"] == "insufficient_canonical_mapping_coverage"
    assert blocked["chase_evidence"]["unresolved_ev_share"] == .4
    assert blocked["chase_evidence"]["intentional_non_pokemon_ev"] == .2


def test_public_explanation_is_backend_structured_and_ev_is_context_only():
    result = compute_universal_set_desirability_v4(
        [subject(25, "Pikachu", 90)], [card(25, "Pikachu SIR", 1)]
    )
    assert "pokemon_desirability" in result["direct_score_inputs"]
    assert "card_ev_contribution" in result["chase_priority_inputs"]
    assert "ev_contribution" in result["direct_arithmetic_excluded_inputs"]
    assert result["modeled_subjects"][0]["representative_chase_card"]["card_name"] == "Pikachu SIR"
