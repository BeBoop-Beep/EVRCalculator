from backend.desirability.collector_component_rankings import (
    METHODOLOGY_VERSION, build_component_ranking_rows, build_raw_component_diagnostics,
)
from backend.scripts.build_pokemon_collector_appeal_v6_corrected_successor import pokemon_d


def card(set_id, card_id, identity, policy="pokemon", baseline=50, play=50, artist=50):
    return {"set_id": set_id, "pokemon_canonical_card_id": card_id, "subject_policy": policy,
            "subject_baseline_score": baseline, "playability_score": play,
            "artist_recognition_score": artist,
            "component_inputs_json": {"subjectIdentity": identity}}


def test_duplicate_printings_do_not_increase_pure_subject_strength():
    one = [card("s", "1", "Pikachu")]
    duplicate = one + [card("s", "2", "Pikachu")]
    assert build_raw_component_diagnostics(one)["s"]["pokemonAppeal"] == build_raw_component_diagnostics(duplicate)["s"]["pokemonAppeal"]


def test_pure_subjects_exclude_lifts_and_ablation_respects_ordered_headroom():
    rows = [card("s", "1", "Pikachu", baseline=40, play=80, artist=90),
            card("s", "2", "Iono", policy="trainer", baseline=70, play=None, artist=60)]
    values = build_raw_component_diagnostics(rows)["s"]
    changed = [card("s", "1", "Pikachu", baseline=40, play=0, artist=0),
               card("s", "2", "Iono", policy="trainer", baseline=70, play=0, artist=0)]
    pure = build_raw_component_diagnostics(changed)["s"]
    assert values["pokemonAppeal"] == pure["pokemonAppeal"]
    assert values["trainerAppeal"] == pure["trainerAppeal"]
    assert values["artistImpact"] > 0
    assert values["playabilityImpact"] > 0


def test_exact_artist_and_playability_ablation_recalculates_artist_headroom():
    values = build_raw_component_diagnostics([card("s", "1", "Pikachu", baseline=40, play=80, artist=90)])["s"]
    after_play = 40 + (100 - 40) * .20 * .80
    full = after_play + (100 - after_play) * .10 * .90
    without_play = 40 + (100 - 40) * .10 * .90
    assert abs(values["artistImpact"] - (pokemon_d([full])[0] - pokemon_d([after_play])[0])) < 1e-12
    assert abs(values["playabilityImpact"] - (pokemon_d([full])[0] - pokemon_d([without_play])[0])) < 1e-12


def test_missing_is_unavailable_not_zero_and_ranking_is_deterministic():
    rows = [card("b", "2", "B", baseline=60), card("a", "1", "A", baseline=60),
            card("c", "3", "", baseline=None, play=None, artist=None)]
    ranked = build_component_ranking_rows(rows, "run", eligible_set_ids={"a", "b", "c"})
    by_set = {row["set_id"]: row for row in ranked}
    assert by_set["a"]["drivers_json"]["pokemonAppeal"]["rank"] == 1
    assert by_set["b"]["drivers_json"]["pokemonAppeal"]["rank"] == 2
    assert by_set["c"]["drivers_json"]["pokemonAppeal"]["rawValue"] is None
    assert by_set["c"]["drivers_json"]["pokemonAppeal"]["status"] == "unavailable"
    assert all(row["model_run_id"] == "run" and row["methodology_version"] == METHODOLOGY_VERSION for row in ranked)


def test_unsupported_catalog_set_cannot_shift_rank_or_public_score():
    supported = [card("ranked-a", "1", "A", baseline=80), card("ranked-b", "2", "B", baseline=60)]
    before = build_component_ranking_rows(
        supported, "run", eligible_set_ids={"ranked-a", "ranked-b"}
    )
    after = build_component_ranking_rows(
        supported + [card("mcdonalds-unsupported", "3", "Extreme", baseline=100, artist=100)],
        "run", eligible_set_ids={"ranked-a", "ranked-b"},
    )
    assert before == after
    assert {row["set_id"] for row in after} == {"ranked-a", "ranked-b"}
    assert all(row["drivers_json"]["pokemonAppeal"]["cohortSize"] == 2 for row in after)
