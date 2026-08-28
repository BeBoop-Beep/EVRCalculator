import math

import pytest

from backend.desirability.card_appeal import TREATMENT_SCORE_RULES_V1, get_treatment_score
from backend.desirability.card_treatment_prestige_v2 import (
    common_support_bounds, log_pull_odds, pairwise_superiority_scores,
    positive_log_price, resolve_treatment_identity,
)
from backend.scripts.build_card_treatment_prestige_v2_study import (
    dimension_table, graph_summary, matched_experiment_audit,
    normalize_dimension, pairwise_overlap, support_audit,
)


def test_taxonomy_normalizes_without_numeric_score():
    value = resolve_treatment_identity(rarity="Special Illustration Rare")
    assert value.treatment_key == "special_illustration_rare"
    assert not hasattr(value, "score")


def test_variant_modifiers_are_identity_not_a_plain_rarity_fallback():
    value = resolve_treatment_identity(rarity="Common", printing_type="Reverse Holo", special_type="Master Ball")
    assert value.treatment_key == "common__reverse_holo__master_ball"


def test_unknown_treatment_fails_closed():
    value = resolve_treatment_identity(rarity="Amazing Unknown Future Treatment")
    assert value.treatment_key is None
    assert value.status == "unmapped_treatment"


def test_log_price_and_pull_odds_enforce_positive_valid_values():
    assert positive_log_price(math.e) == pytest.approx(1)
    assert positive_log_price(0) is None
    assert log_pull_odds(.001) == pytest.approx(math.log(1000))
    assert log_pull_odds(1000) == pytest.approx(math.log(1000))
    assert log_pull_odds(0) is None


def test_pairwise_superiority_formula_exact_synthetic_case():
    draws = {"A": [3, 3, 3, 3], "B": [2, 0, 2, 0], "C": [1, 1, 1, 1]}
    scores = pairwise_superiority_scores(draws)
    assert scores == {"A": 10.0, "B": 2.5, "C": 2.5}


def test_common_support_is_intersection_of_group_quantiles():
    assert common_support_bounds({"a": range(11), "b": range(5, 16)}, lower=0, upper=1) == (5.0, 10.0)


def test_v1_remains_historically_reproducible():
    assert ("special illustration rare", 96.0) in TREATMENT_SCORE_RULES_V1
    assert get_treatment_score("Special Illustration Rare") == 96.0
    assert get_treatment_score("unmatched historical label") == 30.0


def test_research_dimensions_are_unicode_safe_and_keep_unknown_explicit():
    assert normalize_dimension("Pokémon Tool") == "pokemon_tool"
    table = dimension_table([{"printing_finish": None}, {"printing_finish": "holo"}], "printing_finish")
    assert [row["value"] for row in table] == ["__unknown__", "holo"]


def test_common_support_audit_fails_when_scarcity_bands_are_separated():
    rows = ([{"treatment": "normal", "exact_pull": .1, "log_odds": x} for x in range(10)] +
            [{"treatment": "reverse", "exact_pull": .01, "log_odds": x} for x in range(20, 30)])
    result = support_audit(rows, "treatment")["global"]
    assert result["common_support_bounds_log_odds"] is None
    assert result["common_support_coverage"] == 0


def test_pairwise_gate_can_identify_local_overlap_without_universal_support():
    rows=[]
    for treatment,offset in (("a",0),("b",1),("c",100)):
        for i in range(60):
            rows.append({"treatment":treatment,"log_odds":offset+i/10,"exact_pull":.01,
                "set_id":f"s{i%6}","era_id":"e1","canonical_card_id":f"{treatment}{i}",
                "subject_ids":[f"p{i%25}"]})
    matrix=pairwise_overlap(rows,"treatment")
    classes={(x["treatment_a"],x["treatment_b"]):x["classification"] for x in matrix}
    assert classes[("a","b")]=="directly_identifiable_pair"
    assert classes[("a","c")]=="unsupported_pair"
    graph=graph_summary(matrix)
    assert len(graph["direct_edges"])==1
    assert ["a","b"] in graph["connected_components"]


def test_matched_ratio_windows_do_not_imply_quasi_experiment():
    base={"canonical_card_id":"c","set_id":"s","subject_ids":["p"],"priced":True,
          "current_run_id":"r","card_name":"Card","card_number":"1","artist":"A","mechanic_or_card_form":"basic"}
    result=matched_experiment_audit([{**base,"variant_id":"v1","combined_treatment_key":"normal","exact_pull":.1},
                                     {**base,"variant_id":"v2","combined_treatment_key":"holo","exact_pull":.095}])
    assert result["within_10_pct"]==1
    assert result["quasi_experiment_status"].startswith("diagnostic_candidates_only")
